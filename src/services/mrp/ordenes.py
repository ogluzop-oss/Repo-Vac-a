"""
MRP-D/E — Ordenes de fabricacion + integracion con el KARDEX EXISTENTE (no stock paralelo).

Ciclo: borrador -> planificada -> liberada -> en_curso -> (pausada) -> finalizada / cancelada.
Consumo de componentes  = kardex.SALIDA_PRODUCCION + lotes.consumir_fefo (FEFO real).
Alta de producto term.   = kardex.ENTRADA_PRODUCCION + lotes.registrar_entrada (lote de OF).
Auditado (FAB_*). Multiempresa. Idempotente en consumo/produccion.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id, tienda_actual_id

logger = logging.getLogger("mrp.ordenes")
ESTADOS = ("borrador", "planificada", "liberada", "en_curso", "pausada", "finalizada", "cancelada")
_TRANS = {
    "borrador": {"planificada", "cancelada"},
    "planificada": {"liberada", "cancelada"},
    "liberada": {"en_curso", "cancelada"},
    "en_curso": {"pausada", "finalizada", "cancelada"},
    "pausada": {"en_curso", "cancelada"},
}


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.4): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.produccion.identidad_produccion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_orden(articulo_final, cantidad, *, id_almacen=None, fecha_prevista=None,
                responsable=None, id_empresa=None) -> int | None:
    """Crea una OF en borrador: explosiona la BOM activa en of_consumos y copia la ruta en of_operaciones."""
    eid = _emp(id_empresa)
    from src.services.mrp import bom as _bom, centros as _cen
    b = _bom.bom_activa(articulo_final, id_empresa=eid)
    ruta = _cen.ruta_de_articulo(articulo_final, id_empresa=eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ordenes_fabricacion (id_empresa, articulo_final, id_bom, id_ruta, "
                        "cantidad, id_almacen, fecha_prevista, responsable) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, articulo_final, (b or {}).get("id"), (ruta or {}).get("id"),
                         cantidad, id_almacen, fecha_prevista, responsable))
            oid = cur.lastrowid
            cur.execute("UPDATE ordenes_fabricacion SET codigo=%s WHERE id=%s", (f"OF{oid:06d}", oid))
            # of_consumos a partir de la explosion de primer nivel de la BOM.
            if b:
                base = float(b.get("cantidad_base") or 1) or 1
                factor = float(cantidad) / base
                cur.execute("SELECT componente, cantidad, merma_pct FROM bom_lineas WHERE id_bom=%s "
                            "AND es_alternativo=0", (b["id"],))
                for ln in cur.fetchall():
                    ln = list(ln.values()) if isinstance(ln, dict) else ln
                    plan = float(ln[1]) * factor * (1 + float(ln[2] or 0) / 100)
                    cur.execute("INSERT INTO of_consumos (id_empresa, id_of, componente, cantidad_plan) "
                                "VALUES (%s,%s,%s,%s)", (eid, oid, ln[0], round(plan, 4)))
            # of_operaciones a partir de la ruta.
            if ruta:
                cur.execute("SELECT secuencia, nombre, id_centro FROM operaciones_fabricacion WHERE id_ruta=%s "
                            "ORDER BY secuencia", (ruta["id"],))
                for op in cur.fetchall():
                    op = list(op.values()) if isinstance(op, dict) else op
                    cur.execute("INSERT INTO of_operaciones (id_empresa, id_of, secuencia, nombre, id_centro) "
                                "VALUES (%s,%s,%s,%s,%s)", (eid, oid, op[0], op[1], op[2]))
            conn.commit()
        log_auditoria("mrp", "FAB_OF_CREATED", "ordenes_fabricacion", f"of={oid} {articulo_final} x{cantidad}")
        return oid
    except Exception as e:
        logger.error("crear_orden: %s", e)
        return None


def _estado(oid):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado FROM ordenes_fabricacion WHERE id=%s", (oid,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def cambiar_estado(oid, nuevo, *, id_empresa=None) -> dict:
    if nuevo not in ESTADOS:
        raise ValueError(f"estado invalido: {nuevo}")
    actual = _estado(oid)
    if actual is None:
        return {"ok": False, "error": "OP inexistente"}
    if nuevo != actual and nuevo not in _TRANS.get(actual, set()):
        return {"ok": False, "error": f"transicion {actual}->{nuevo} no permitida"}
    sets = "estado=%s"
    extra = []
    if nuevo == "en_curso" and actual != "pausada":
        sets += ", fecha_inicio=%s"; extra = [_dt.datetime.now()]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ordenes_fabricacion SET {sets} WHERE id=%s", (nuevo, *extra, oid))
            conn.commit()
        log_auditoria("mrp", f"FAB_OF_{nuevo.upper()}", "ordenes_fabricacion", f"of={oid}")
        _evento_workflow(oid, nuevo)
        return {"ok": True, "estado": nuevo}
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return {"ok": False, "error": str(e)}


def planificar(oid, **k): return cambiar_estado(oid, "planificada", **k)
def liberar(oid, **k): return cambiar_estado(oid, "liberada", **k)
def iniciar(oid, **k): return cambiar_estado(oid, "en_curso", **k)
def pausar(oid, **k): return cambiar_estado(oid, "pausada", **k)
def cancelar(oid, **k): return cambiar_estado(oid, "cancelada", **k)


def consumir_materiales(oid, *, id_empresa=None, usuario=None) -> dict:
    """Consume los componentes de la OF del KARDEX (FEFO + movimiento auditado). Idempotente."""
    eid = _emp(id_empresa)
    from src.db import kardex, lotes
    consumidos, faltantes = [], []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_almacen FROM ordenes_fabricacion WHERE id=%s", (oid,))
            ralm = cur.fetchone()
            id_almacen = (ralm[0] if not isinstance(ralm, dict) else list(ralm.values())[0]) if ralm else None
            cur.execute("SELECT id, componente, cantidad_plan, consumido FROM of_consumos WHERE id_of=%s", (oid,))
            filas = [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("consumir_materiales/lectura: %s", e)
        return {"ok": False, "error": str(e)}
    for f in filas:
        if f.get("consumido"):
            continue
        comp, cant = f["componente"], float(f["cantidad_plan"])
        res = lotes.consumir_fefo(comp, cant, tipo="SALIDA_PRODUCCION", id_empresa=eid,
                                  id_documento=f"OF:{oid}", usuario=usuario, id_almacen=id_almacen,
                                  observaciones=f"Consumo OP {oid}", idempotente=True)
        consumido = res.get("consumido", 0)
        if not consumido:        # articulo sin gestion por lotes -> movimiento directo de kardex
            kardex.registrar_movimiento(comp, "SALIDA_PRODUCCION", int(cant), id_documento=f"OF:{oid}",
                                        usuario=usuario, observaciones=f"Consumo OP {oid}",
                                        id_empresa=eid, id_almacen_origen=id_almacen, idempotente=True)
            consumido = cant
        if res.get("faltante"):
            faltantes.append({"componente": comp, "faltante": res["faltante"]})
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE of_consumos SET cantidad_real=%s, consumido=1 WHERE id=%s",
                            (consumido, f["id"]))
                conn.commit()
        except Exception:
            pass
        consumidos.append({"componente": comp, "cantidad": consumido})
    if faltantes:
        log_auditoria("mrp", "FAB_OF_ROTURA_MATERIALES", "of_consumos", f"of={oid} {faltantes}")
        _alerta_rotura(oid, faltantes, eid)
    log_auditoria("mrp", "FAB_OF_CONSUMO", "of_consumos", f"of={oid} n={len(consumidos)}")
    return {"ok": True, "consumidos": consumidos, "faltantes": faltantes}


def listar_consumos(oid, *, id_empresa=None) -> list:
    """Checklist de solo lectura de los materiales previstos/consumidos de una OF — para el móvil."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM of_consumos WHERE id_of=%s AND id_empresa=%s ORDER BY id",
                        (oid, eid))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_consumos: %s", e)
        return []


def listar_producciones(oid, *, id_empresa=None) -> list:
    """Historial de solo lectura de los lotes ya producidos de una OF — para el móvil."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM of_produccion WHERE id_of=%s AND id_empresa=%s ORDER BY fecha DESC",
                        (oid, eid))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_producciones: %s", e)
        return []


def registrar_produccion(oid, cantidad, *, lote=None, id_empresa=None, usuario=None,
                         id_centro_destino=None) -> dict:
    """Da de alta producto terminado en el KARDEX (ENTRADA_PRODUCCION + lote de OF).

    `id_centro_destino` (migr. 0321, petición explícita — flujo Producción -> Logística
    automático): si se indica (CUALQUIER centro registrado de la empresa, elegido con el buscador de
    `gui.components.completer_centros`), tras registrar la producción se genera AUTOMÁTICAMENTE el
    documento logístico de "mercancía disponible para expedición" (`db.logistica.
    registrar_documento_produccion`, evitando duplicidad de entradas manuales) y se evalúa el
    cross-docking a una ruta de reparto ya abierta hacia ese centro
    (`services.logistica.cross_docking_rutas.evaluar_cross_docking_automatico`). Best-effort: un
    fallo aquí nunca deshace ni bloquea el alta de producción ya confirmada."""
    eid = _emp(id_empresa)
    from src.db import kardex, lotes
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT articulo_final, id_almacen, cantidad_producida FROM ordenes_fabricacion WHERE id=%s",
                        (oid,))
            r = cur.fetchone()
        if not r:
            return {"ok": False, "error": "OP inexistente"}
        r = list(r.values()) if isinstance(r, dict) else r
        articulo, id_almacen = r[0], r[1]
        lote = lote or f"OF{oid:06d}"
        lid = lotes.registrar_entrada(articulo, lote, int(cantidad), id_empresa=eid, origen="produccion",
                                      id_documento=f"OF:{oid}", usuario=usuario, id_almacen=id_almacen)
        if not lid:        # articulo sin lotes -> movimiento directo de kardex
            kardex.registrar_movimiento(articulo, "ENTRADA_PRODUCCION", int(cantidad), id_documento=f"OF:{oid}",
                                        usuario=usuario, observaciones=f"Produccion OP {oid}",
                                        id_empresa=eid, id_almacen_destino=id_almacen)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO of_produccion (id_empresa, id_of, cantidad, lote) VALUES (%s,%s,%s,%s)",
                        (eid, oid, cantidad, lote))
            id_produccion = cur.lastrowid
            cur.execute("UPDATE ordenes_fabricacion SET cantidad_producida=cantidad_producida+%s, "
                        "lote_destino=%s WHERE id=%s", (cantidad, lote, oid))
            if id_centro_destino:
                cur.execute("UPDATE ordenes_fabricacion SET id_centro_destino=%s WHERE id=%s",
                            (id_centro_destino, oid))
            conn.commit()
        log_auditoria("mrp", "FAB_OF_PRODUCCION", "of_produccion", f"of={oid} {articulo} +{cantidad}")
        resultado = {"ok": True, "id_produccion": id_produccion, "articulo": articulo, "cantidad": cantidad,
                    "lote": lote}
        if id_centro_destino:
            resultado["logistica"] = _generar_entrada_logistica_produccion(
                oid, articulo, cantidad, id_almacen, id_centro_destino, id_empresa=eid, usuario=usuario)
        return resultado
    except Exception as e:
        logger.error("registrar_produccion: %s", e)
        return {"ok": False, "error": str(e)}


def _generar_entrada_logistica_produccion(oid, articulo, cantidad, id_almacen, id_centro_destino, *,
                                          id_empresa, usuario) -> dict:
    """Genera el documento logístico de producción + evalúa el cross-dock a ruta — aislado en su
    propia función (best-effort, nunca propaga una excepción hacia `registrar_produccion`: el alta de
    producción ya quedó confirmada en el KARDEX antes de llegar aquí)."""
    try:
        from src.db import centros, logistica
        nombre_destino = (centros.obtener_centro(id_centro_destino) or {}).get("nombre_centro") or id_centro_destino
        r = logistica.registrar_documento_produccion(
            oid, origen=f"PRODUCCION OF-{oid}", destino=nombre_destino, usuario=usuario,
            lineas=[{"codigo": articulo, "nombre": articulo, "cantidad": cantidad}],
            id_centro_destino=id_centro_destino, id_almacen_origen=id_almacen, id_empresa=id_empresa)
        if r.get("ok") and not r.get("ya_existia"):
            from src.services.logistica import cross_docking_rutas as XD
            r["cross_docking"] = XD.evaluar_cross_docking_automatico(
                r["id_documento"], id_empresa=id_empresa, usuario=usuario)
        return r
    except Exception as e:
        logger.warning("_generar_entrada_logistica_produccion(OF=%s): %s", oid, e)
        return {"ok": False, "error": "error_interno"}


def finalizar(oid, *, id_empresa=None, usuario=None, registrar_costes=True) -> dict:
    """Finaliza la OF: marca fin, calcula costes reales y desviacion."""
    eid = _emp(id_empresa)
    r = cambiar_estado(oid, "finalizada", id_empresa=eid)
    if not r.get("ok"):
        return r
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ordenes_fabricacion SET fecha_fin=%s WHERE id=%s", (_dt.datetime.now(), oid))
            conn.commit()
    except Exception:
        pass
    if registrar_costes:
        try:
            from src.services.mrp import costes
            r["costes"] = costes.calcular_coste_real_of(oid, id_empresa=eid)
        except Exception as e:
            logger.debug("costes finalizar: %s", e)
    return r


def obtener_of(oid) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ordenes_fabricacion WHERE id=%s", (oid,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_of: %s", e)
        return None


def listar(*, estado=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM ordenes_fabricacion WHERE id_empresa=%s"
    p = [eid]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def _evento_workflow(oid, estado):
    try:
        from src.services import notificaciones
        if estado in ("liberada", "finalizada"):
            notificaciones.emitir("fabricacion", f"OP {oid} {estado}", "", modulo="mrp",
                                  roles=["ADMINISTRADOR"])
    except Exception:
        pass


def _alerta_rotura(oid, faltantes, eid):
    try:
        from src.services.observabilidad import alertas_tecnicas
        alertas_tecnicas.emitir("rotura_materiales", f"OP {oid}: {faltantes}", severidad="alta", id_empresa=eid)
    except Exception:
        pass
