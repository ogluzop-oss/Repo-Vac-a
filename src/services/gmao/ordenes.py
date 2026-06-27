"""
GMAO-C/D/E — Ordenes de trabajo (preventiva/correctiva/predictiva) con ciclo de estados,
consumo/reserva/devolucion de REPUESTOS por el KARDEX existente (no inventario paralelo) y costes.

Ciclo: borrador -> abierta -> asignada -> en_curso -> (pausada) -> finalizada / cancelada.
Auditado (OT_*). Multiempresa.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("gmao.ordenes")
TIPOS = ("preventiva", "correctiva", "predictiva")
ESTADOS = ("borrador", "abierta", "asignada", "en_curso", "pausada", "finalizada", "cancelada")
_TRANS = {
    "borrador": {"abierta", "cancelada"},
    "abierta": {"asignada", "en_curso", "cancelada"},
    "asignada": {"en_curso", "cancelada"},
    "en_curso": {"pausada", "finalizada", "cancelada"},
    "pausada": {"en_curso", "cancelada"},
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_ot(*, tipo="correctiva", id_activo=None, id_plan=None, descripcion=None, prioridad="media",
             tecnico=None, id_almacen=None, fecha_prevista=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    estado = "abierta" if tipo == "preventiva" else "borrador"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ordenes_trabajo (id_empresa, tipo, id_activo, id_plan, descripcion, "
                        "prioridad, estado, tecnico, id_almacen, fecha_prevista) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, tipo, id_activo, id_plan, descripcion, prioridad, estado, tecnico,
                         id_almacen, fecha_prevista))
            oid = cur.lastrowid
            cur.execute("UPDATE ordenes_trabajo SET codigo=%s WHERE id=%s", (f"OT{oid:06d}", oid))
            conn.commit()
        if id_activo:
            from src.services.gmao import activos
            activos._historial(id_activo, "OT_CREADA", f"OT {oid} {tipo}", eid, id_ot=oid)
        log_auditoria("gmao", "OT_CREADA", "ordenes_trabajo", f"ot={oid} {tipo}")
        return oid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_ot: %s", e)
        return None


def _estado(oid):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado FROM ordenes_trabajo WHERE id=%s", (oid,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def cambiar_estado(oid, nuevo, *, tecnico=None, id_empresa=None) -> dict:
    if nuevo not in ESTADOS:
        raise ValueError(f"estado invalido: {nuevo}")
    actual = _estado(oid)
    if actual is None:
        return {"ok": False, "error": "OT inexistente"}
    if nuevo != actual and nuevo not in _TRANS.get(actual, set()):
        return {"ok": False, "error": f"transicion {actual}->{nuevo} no permitida"}
    sets, extra = "estado=%s", []
    if nuevo == "asignada" and tecnico is not None:
        sets += ", tecnico=%s"; extra = [tecnico]
    elif nuevo == "en_curso" and actual != "pausada":
        sets += ", fecha_inicio=%s"; extra = [_dt.datetime.now()]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ordenes_trabajo SET {sets} WHERE id=%s", (nuevo, *extra, oid))
            conn.commit()
        log_auditoria("gmao", f"OT_{nuevo.upper()}", "ordenes_trabajo", f"ot={oid}")
        _evento(oid, nuevo, eid=_emp(id_empresa))
        return {"ok": True, "estado": nuevo}
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado OT: %s", e)
        return {"ok": False, "error": str(e)}


def asignar(oid, tecnico, **k): return cambiar_estado(oid, "asignada", tecnico=tecnico, **k)
def iniciar(oid, **k): return cambiar_estado(oid, "en_curso", **k)
def cancelar(oid, **k): return cambiar_estado(oid, "cancelada", **k)


# ── Repuestos (GMAO-D) — usan el KARDEX existente ─────────────────────────────
def añadir_repuesto(oid, referencia, cantidad, *, coste_unitario=0, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ot_recursos (id_empresa, id_ot, tipo, referencia, cantidad, coste_unitario) "
                        "VALUES (%s,%s,'repuesto',%s,%s,%s)", (eid, oid, referencia, cantidad, coste_unitario))
            rid = cur.lastrowid
            conn.commit()
        return rid
    except Exception as e:
        logger.error("añadir_repuesto: %s", e)
        return None


def consumir_repuestos(oid, *, id_empresa=None, usuario=None) -> dict:
    """Consume del KARDEX (FEFO + movimiento auditado) los repuestos de la OT no consumidos."""
    eid = _emp(id_empresa)
    from src.db import kardex, lotes
    consumidos, faltantes = [], []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_almacen FROM ordenes_trabajo WHERE id=%s", (oid,))
            r = cur.fetchone()
            id_almacen = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            cur.execute("SELECT id, referencia, cantidad, consumido FROM ot_recursos WHERE id_ot=%s "
                        "AND tipo='repuesto'", (oid,))
            filas = [_fila(cur, x) for x in cur.fetchall()]
    except Exception as e:
        logger.error("consumir_repuestos/lectura: %s", e)
        return {"ok": False, "error": str(e)}
    for f in filas:
        if f.get("consumido"):
            continue
        ref, cant = f["referencia"], float(f["cantidad"])
        res = lotes.consumir_fefo(ref, cant, tipo="SALIDA_PRODUCCION", id_empresa=eid,
                                  id_documento=f"OT:{oid}", usuario=usuario, id_almacen=id_almacen,
                                  observaciones=f"Repuesto OT {oid}", idempotente=True)
        if not res.get("consumido"):
            kardex.registrar_movimiento(ref, "SALIDA_PRODUCCION", int(cant), id_documento=f"OT:{oid}",
                                        usuario=usuario, observaciones=f"Repuesto OT {oid}",
                                        id_empresa=eid, id_almacen_origen=id_almacen, idempotente=True)
        if res.get("faltante"):
            faltantes.append({"referencia": ref, "faltante": res["faltante"]})
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE ot_recursos SET consumido=1 WHERE id=%s", (f["id"],))
                conn.commit()
        except Exception:
            pass
        consumidos.append({"referencia": ref, "cantidad": cant})
    log_auditoria("gmao", "OT_REPUESTOS_CONSUMIDOS", "ot_recursos", f"ot={oid} n={len(consumidos)}")
    return {"ok": True, "consumidos": consumidos, "faltantes": faltantes}


def devolver_repuesto(oid, referencia, cantidad, *, id_empresa=None, usuario=None) -> bool:
    """Devuelve repuesto sobrante al stock (entrada en kardex/lotes)."""
    eid = _emp(id_empresa)
    from src.db import lotes
    try:
        lotes.registrar_entrada(referencia, f"DEVOT{oid}", int(cantidad), id_empresa=eid,
                                origen="devolucion_ot", id_documento=f"OT:{oid}", usuario=usuario)
        log_auditoria("gmao", "OT_REPUESTO_DEVUELTO", "ot_recursos", f"ot={oid} {referencia} +{cantidad}")
        return True
    except Exception as e:
        logger.error("devolver_repuesto: %s", e)
        return False


def finalizar(oid, *, id_empresa=None, horas_mano_obra=0, coste_hora=30, coste_desplazamiento=0,
              coste_externo=0, usuario=None) -> dict:
    """Finaliza la OT: consume repuestos pendientes, calcula costes (GMAO-E) y cierra activo si aplica."""
    eid = _emp(id_empresa)
    consumir_repuestos(oid, id_empresa=eid, usuario=usuario)
    r = cambiar_estado(oid, "finalizada", id_empresa=eid)
    if not r.get("ok"):
        return r
    costes = _calcular_costes(oid, horas_mano_obra, coste_hora, coste_desplazamiento, coste_externo, eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ordenes_trabajo SET fecha_fin=%s WHERE id=%s", (_dt.datetime.now(), oid))
            cur.execute("SELECT id_activo FROM ordenes_trabajo WHERE id=%s", (oid,))
            ra = cur.fetchone()
            id_activo = (ra[0] if not isinstance(ra, dict) else list(ra.values())[0]) if ra else None
            conn.commit()
        if id_activo:
            from src.services.gmao import activos
            activos._historial(id_activo, "OT_FINALIZADA", f"OT {oid}", eid, id_ot=oid)
    except Exception:
        pass
    r["costes"] = costes
    return r


def _calcular_costes(oid, horas, coste_hora, desplaz, externo, eid):
    materiales = 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(cantidad*coste_unitario),0) FROM ot_recursos WHERE id_ot=%s "
                        "AND tipo='repuesto'", (oid,))
            r = cur.fetchone()
            materiales = float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        pass
    mo = float(horas) * float(coste_hora)
    real = round(mo + materiales + float(desplaz) + float(externo), 4)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO costes_ot (id_empresa, id_ot, coste_mano_obra, coste_materiales, "
                        "coste_desplazamiento, coste_externo, coste_real) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE coste_mano_obra=VALUES(coste_mano_obra), "
                        "coste_materiales=VALUES(coste_materiales), coste_desplazamiento=VALUES(coste_desplazamiento), "
                        "coste_externo=VALUES(coste_externo), coste_real=VALUES(coste_real), actualizado=NOW()",
                        (eid, oid, mo, materiales, desplaz, externo, real))
            conn.commit()
        log_auditoria("gmao", "OT_COSTE", "costes_ot", f"ot={oid} real={real}")
    except Exception as e:
        logger.error("_calcular_costes: %s", e)
    return {"mano_obra": mo, "materiales": materiales, "desplazamiento": float(desplaz),
            "externo": float(externo), "coste_real": real}


def obtener(oid) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ordenes_trabajo WHERE id=%s", (oid,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener OT: %s", e)
        return None


def listar(*, estado=None, tipo=None, id_activo=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM ordenes_trabajo WHERE id_empresa=%s"
    p = [eid]
    for col, val in (("estado", estado), ("tipo", tipo), ("id_activo", id_activo)):
        if val is not None:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar OT: %s", e)
        return []


def _evento(oid, estado, eid=None):
    try:
        from src.services import notificaciones
        if estado in ("abierta", "finalizada"):
            notificaciones.emitir("gmao", f"OT {oid} {estado}", "", modulo="gmao",
                                  roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
    except Exception:
        pass
