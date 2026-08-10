"""
Logística PRO (Módulo 6, enriquecimiento). Añade lo ausente: transportistas y expediciones (con
seguimiento/tracking, coste, entregas programadas/parciales). Reutiliza los pedidos/picking existentes
como origen y las `incidencias_logisticas` ya existentes. Auditado, multiempresa. No duplica.
"""

import datetime as _dt
import logging

logger = logging.getLogger("logistica.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.logistica.identidad_logistica import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="logistica_expediciones"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("logistica", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Transportistas ──────────────────────────────────────────────────────────
def crear_transportista(nombre, *, contacto=None, telefono=None, url_seguimiento=None,
                        id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO logistica_transportistas (id_empresa, nombre, contacto, telefono, "
                        "url_seguimiento) VALUES (%s,%s,%s,%s,%s)",
                        (emp, nombre[:120], contacto, telefono, url_seguimiento))
            tid = cur.lastrowid
            c.commit()
        _audit("TRANSPORTISTA_ALTA", f"{tid}:{nombre}", "logistica_transportistas")
        return tid
    except Exception as e:
        logger.error("crear_transportista: %s", e)
        return None


def transportistas(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM logistica_transportistas WHERE id_empresa<=>%s AND activo=1", (emp,))
            return _filas(cur)
    except Exception as e:
        logger.error("transportistas: %s", e)
        return []


# ── Expediciones ────────────────────────────────────────────────────────────
def crear_expedicion(*, referencia=None, id_transportista=None, origen="pedido", id_documento=None,
                     direccion=None, coste=0, parcial=False, fecha_programada=None,
                     id_empresa=None) -> int | None:
    """Crea una expedición (envío de salida). Origen puede ser un pedido/venta o un picking (M5)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO logistica_expediciones (id_empresa, referencia, id_transportista, "
                        "origen, id_documento, direccion, coste, parcial, fecha_programada) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, referencia, id_transportista, origen,
                         str(id_documento) if id_documento is not None else None, direccion,
                         float(coste or 0), 1 if parcial else 0, fecha_programada))
            eid = cur.lastrowid
            c.commit()
        _audit("EXPEDICION_CREADA", f"{eid}:ref{referencia} parcial={parcial}")
        return eid
    except Exception as e:
        logger.error("crear_expedicion: %s", e)
        return None


_ESTADOS = ("PREPARACION", "ENVIADA", "EN_TRANSITO", "ENTREGADA", "INCIDENCIA", "DEVUELTA")


def actualizar_seguimiento(id_expedicion, *, estado=None, tracking=None, id_empresa=None) -> dict:
    """Actualiza el seguimiento/tracking y el estado de la expedición. Marca tiempos de envío/entrega."""
    if estado and estado not in _ESTADOS:
        return {"ok": False, "motivo": "estado inválido"}
    sets, params = [], []
    if tracking is not None:
        sets.append("tracking=%s"); params.append(tracking)
    if estado:
        sets.append("estado=%s"); params.append(estado)
        if estado == "ENVIADA":
            sets.append("fecha_envio=NOW()")
        elif estado == "ENTREGADA":
            sets.append("fecha_entrega=NOW()")
    if not sets:
        return {"ok": False, "motivo": "nada que actualizar"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"UPDATE logistica_expediciones SET {', '.join(sets)} WHERE id=%s",
                        (*params, id_expedicion))
            c.commit()
        _audit("EXPEDICION_SEGUIMIENTO", f"{id_expedicion}:{estado or ''}/{tracking or ''}")
        return {"ok": True}
    except Exception as e:
        logger.error("actualizar_seguimiento: %s", e)
        return {"ok": False, "motivo": str(e)}


def registrar_incidencia_expedicion(id_expedicion, descripcion, *, id_empresa=None) -> dict:
    """Registra una incidencia de expedición REUTILIZANDO `incidencias_logisticas` existente (si está)
    y marca la expedición en estado INCIDENCIA."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            try:
                cur.execute("INSERT INTO incidencias_logisticas (id_empresa, descripcion, origen) "
                            "VALUES (%s,%s,%s)", (emp, descripcion[:255], f"expedicion:{id_expedicion}"))
            except Exception:
                pass   # esquema de incidencias distinto → solo se marca la expedición
            cur.execute("UPDATE logistica_expediciones SET estado='INCIDENCIA' WHERE id=%s", (id_expedicion,))
            c.commit()
        _audit("EXPEDICION_INCIDENCIA", f"{id_expedicion}")
        return {"ok": True}
    except Exception as e:
        logger.error("registrar_incidencia_expedicion: %s", e)
        return {"ok": False, "motivo": str(e)}


def expediciones(id_empresa=None, *, estado=None, programadas=False) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM logistica_expediciones WHERE id_empresa<=>%s"
            p = [emp]
            if estado:
                q += " AND estado=%s"; p.append(estado)
            if programadas:
                q += " AND fecha_programada IS NOT NULL AND fecha_programada>=%s"
                p.append(_dt.date.today().isoformat())
            q += " ORDER BY COALESCE(fecha_programada, creada) DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("expediciones: %s", e)
        return []


def coste_logistico(id_empresa=None, *, desde=None, hasta=None) -> float:
    """Coste logístico total de las expediciones en el período (reutiliza el campo `coste`)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(coste),0) FROM logistica_expediciones WHERE id_empresa<=>%s "
                        "AND (%s IS NULL OR creada>=%s) AND (%s IS NULL OR creada<=%s)",
                        (emp, desde, desde, hasta, hasta))
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.debug("coste_logistico: %s", e)
        return 0.0
