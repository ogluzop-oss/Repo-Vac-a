"""
Recetas y dispensación (edición Pharmacy). Registra recetas (paciente + líneas de medicamento/posología) y, al
DISPENSAR, descuenta el stock por el motor OFICIAL de salida (`db/salida_stock.salida_stock_oficial` → clamp +
kárdex + FEFO). N7: no introduce una política de salida de stock paralela. Multi-tenant.

La FUNCIÓN es exclusiva de la edición Pharmacy (`verticales.visible("pharmacy.recetas")`); el servicio es general.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, obtener_conexion

logger = logging.getLogger("pharmacy.recetas")

ESTADOS = ("PENDIENTE", "DISPENSADA", "PARCIAL", "ANULADA")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def crear_receta(paciente, items, *, medico=None, cliente_id=None, id_empresa=None, usuario=None,
                 observaciones=None, fecha=None) -> int | None:
    """Registra en el sistema una receta PENDIENTE que un médico EMITIÓ y el paciente presenta (la farmacia
    no la prescribe: la registra para poder dispensarla). `items` = [{'codigo','cantidad','posologia'}].
    Devuelve el id o None. Ver alias `registrar_receta` (terminología correcta del sector)."""
    emp = _emp(id_empresa)
    paciente = (paciente or "").strip()
    if not emp or not paciente:
        return None
    validas = []
    for it in items or []:
        cod = str(it.get("codigo") or "").strip()
        cant = int(it.get("cantidad") or 0)
        if cod and cant > 0:
            validas.append((cod, cant, (it.get("posologia") or None)))
    if not validas:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO recetas (id_empresa, paciente, cliente_id, medico, fecha, estado, "
                        "observaciones, usuario) VALUES (%s,%s,%s,%s,%s,'PENDIENTE',%s,%s)",
                        (emp, paciente, cliente_id, medico, fecha or _dt.date.today(), observaciones,
                         _usuario(usuario)))
            rid = cur.lastrowid
            cur.executemany("INSERT INTO recetas_lineas (id_receta, codigo_articulo, cantidad, posologia) "
                            "VALUES (%s,%s,%s,%s)", [(rid, c, q, p) for c, q, p in validas])
            conn.commit()
        _audit(emp, "RECETA_CREADA", f"receta={rid} paciente={paciente} lineas={len(validas)}")
        return rid
    except Exception as e:
        logger.error("crear_receta: %s", e)
        return None


# La farmacia REGISTRA la receta emitida por un médico (no la "crea"); alias con la terminología del sector.
registrar_receta = crear_receta


def listar_recetas(*, estado=None, id_empresa=None, limite=200) -> list:
    emp = _emp(id_empresa)
    if not emp:
        return []
    q = "SELECT * FROM recetas WHERE id_empresa=%s"
    p = [emp]
    if estado:
        q += " AND estado=%s"
        p.append(estado)
    q += " ORDER BY id DESC LIMIT %s"
    p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, tuple(p))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_recetas: %s", e)
        return []


def obtener_receta(id_receta, *, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM recetas WHERE id=%s AND id_empresa=%s", (id_receta, emp))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM recetas_lineas WHERE id_receta=%s ORDER BY id", (id_receta,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.debug("obtener_receta: %s", e)
        return None


def dispensar(id_receta, *, id_empresa=None, usuario=None) -> dict:
    """Dispensa la receta: descuenta el stock de cada línea por el motor OFICIAL (clamp+kárdex+FEFO). Estado
    DISPENSADA si se entrega todo, PARCIAL si falta stock. Idempotente por línea (usa lo pendiente)."""
    emp = _emp(id_empresa)
    rec = obtener_receta(id_receta, id_empresa=emp)
    if not rec:
        return {"ok": False, "error": "receta no encontrada"}
    if rec["estado"] not in ("PENDIENTE", "PARCIAL"):
        return {"ok": False, "error": f"estado no dispensable: {rec['estado']}"}
    from src.db.salida_stock import salida_stock_oficial
    usr = _usuario(usuario)
    dispensadas, completa = 0, True
    try:
        for ln in rec["lineas"]:
            pend = int(ln["cantidad"]) - int(ln["dispensado"])
            if pend <= 0:
                continue
            sal = salida_stock_oficial(ln["codigo_articulo"], pend, id_documento=f"RX-{id_receta}",
                                       id_empresa=emp, contexto="dispensacion", usuario=usr)
            servido = pend - int((sal or {}).get("faltante") or 0)
            if servido > 0:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE recetas_lineas SET dispensado=dispensado+%s WHERE id=%s",
                                (servido, ln["id"]))
                    conn.commit()
                dispensadas += servido
            if servido < pend:
                completa = False
        estado = "DISPENSADA" if completa else "PARCIAL"
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE recetas SET estado=%s, dispensado=NOW() WHERE id=%s AND id_empresa=%s",
                        (estado, id_receta, emp))
            conn.commit()
        _audit(emp, "RECETA_DISPENSADA", f"receta={id_receta} unidades={dispensadas} estado={estado}")
        return {"ok": True, "estado": estado, "dispensadas": dispensadas}
    except Exception as e:
        logger.error("dispensar: %s", e)
        return {"ok": False, "error": str(e)}


def anular(id_receta, *, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE recetas SET estado='ANULADA' WHERE id=%s AND id_empresa=%s AND estado IN "
                        "('PENDIENTE','PARCIAL')", (id_receta, emp))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("anular: %s", e)
        return False


def _audit(id_empresa, accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("pharmacy", accion, "recetas", f"{id_empresa}: {detalle}")
    except Exception:
        pass
