"""
Auditoría de seguridad del autocobro (Capa 3) — de la caja al ERP.

Captura los metadatos de seguridad de cada venta de autoservicio (intervenciones de peso, anulaciones,
autorizador, duración) y las incidencias por artículo (bloqueo de peso / anulación), y ofrece consultas
de analítica para la detección de merma (shrinkage) y la optimización del máster de productos
(p. ej. detectar que un packaging cambió porque un artículo se bloquea constantemente).

Servicio API-First (sin PyQt), degradable: si las tablas no existen o la BD falla, no rompe la venta.
Reutiliza la conexión y el tenant existentes; no crea motores nuevos.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("tpv.autocobro_seguridad")

TIPO_BLOQUEO_PESO = "BLOQUEO_PESO"
TIPO_ANULACION = "ANULACION"


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _tenant(id_empresa=None, id_tienda=None):
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return (id_empresa or empresa_actual_id(), id_tienda or tienda_actual_id())
    except Exception:
        return (id_empresa, id_tienda)


# ─── Captura (caja → ERP) ─────────────────────────────────────────────────────

def registrar_incidencia(terminal_id, codigo, nombre, tipo=TIPO_BLOQUEO_PESO, *,
                         venta_id=None, id_empresa=None, id_tienda=None) -> bool:
    """Registra una incidencia de seguridad por artículo (bloqueo de peso / anulación). Degradable."""
    emp, tie = _tenant(id_empresa, id_tienda)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO autocobro_incidencias "
                "(id_empresa, id_tienda, terminal_id, venta_id, codigo_articulo, nombre, tipo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (emp, tie, terminal_id, venta_id, str(codigo) if codigo is not None else None,
                 nombre, tipo))
            conn.commit()
        return True
    except Exception as e:
        logger.debug(f"registrar_incidencia degradado: {e}")
        return False


def registrar_venta_seguridad(terminal_id, venta_id, *, intervenciones=0, anulaciones=0,
                              autorizado_por=None, duracion_seg=0, items=0, total=None,
                              id_empresa=None, id_tienda=None) -> bool:
    """Registra el resumen de seguridad de una venta de autocobro (el 'security_logs' del ticket).
    Degradable: nunca rompe el cierre de la venta."""
    emp, tie = _tenant(id_empresa, id_tienda)
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO autocobro_seguridad_log "
                "(id_empresa, id_tienda, terminal_id, venta_id, intervenciones_peso, anulaciones, "
                " autorizado_por, duracion_seg, items, total) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (emp, tie, terminal_id, venta_id, int(intervenciones or 0), int(anulaciones or 0),
                 autorizado_por, int(duracion_seg or 0), int(items or 0), total))
            conn.commit()
        return True
    except Exception as e:
        logger.debug(f"registrar_venta_seguridad degradado: {e}")
        return False


# ─── Analítica (ERP) ──────────────────────────────────────────────────────────

def articulos_conflictivos(*, id_empresa=None, id_tienda=None, dias=90, limite=20,
                           tipo=None) -> list[dict]:
    """Artículos con más incidencias (señal de merma / packaging cambiado). Orden desc por incidencias.
    Devuelve [{'codigo','nombre','incidencias'}]. Degradable → []."""
    emp, tie = _tenant(id_empresa, id_tienda)
    cond = ["creado >= (NOW() - INTERVAL %s DAY)"]
    params: list = [int(dias)]
    if emp:
        cond.append("id_empresa=%s"); params.append(emp)
    if tie:
        cond.append("id_tienda=%s"); params.append(tie)
    if tipo:
        cond.append("tipo=%s"); params.append(tipo)
    params.append(int(limite))
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo_articulo, MAX(nombre) AS nombre, COUNT(*) AS incidencias "
                "FROM autocobro_incidencias WHERE " + " AND ".join(cond) +
                " GROUP BY codigo_articulo ORDER BY incidencias DESC LIMIT %s", tuple(params))
            return [{"codigo": r[0], "nombre": r[1], "incidencias": int(r[2])} for r in cur.fetchall()]
    except Exception as e:
        logger.debug(f"articulos_conflictivos degradado: {e}")
        return []


def resumen(*, id_empresa=None, id_tienda=None, dias=30) -> dict:
    """Métricas agregadas de seguridad del autocobro en los últimos `dias`. Degradable → ceros."""
    emp, tie = _tenant(id_empresa, id_tienda)
    cond = ["creado >= (NOW() - INTERVAL %s DAY)"]
    params: list = [int(dias)]
    if emp:
        cond.append("id_empresa=%s"); params.append(emp)
    if tie:
        cond.append("id_tienda=%s"); params.append(tie)
    base = {"ventas": 0, "intervenciones_peso": 0, "anulaciones": 0,
            "duracion_media_seg": 0.0, "ventas_con_intervencion": 0}
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(intervenciones_peso),0), COALESCE(SUM(anulaciones),0), "
                "COALESCE(AVG(duracion_seg),0), "
                "COALESCE(SUM(CASE WHEN intervenciones_peso>0 THEN 1 ELSE 0 END),0) "
                "FROM autocobro_seguridad_log WHERE " + " AND ".join(cond), tuple(params))
            r = cur.fetchone()
            if r:
                base.update({"ventas": int(r[0]), "intervenciones_peso": int(r[1]),
                             "anulaciones": int(r[2]), "duracion_media_seg": round(float(r[3]), 1),
                             "ventas_con_intervencion": int(r[4])})
    except Exception as e:
        logger.debug(f"resumen degradado: {e}")
    return base
