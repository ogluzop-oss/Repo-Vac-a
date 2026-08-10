"""
FASE 4.11 — Analítica de facturación (KPIs empresariales).

Explota la capa de facturación (facturas_cliente + cliente_suscripciones) con KPIs: facturación
diaria/mensual/anual, MRR/ARR, por tienda/cliente, impagos y morosidad. Mismo patrón que el BI
existente (SQL agregada directa, sin duplicar el Data Warehouse). Tenant-aware (id_empresa).
"""

import logging

logger = logging.getLogger("facturacion.analitica")

# Documentos que cuentan como facturación real (excluye proforma/anulada/rechazada).
_VALIDAS = "estado NOT IN ('anulada','rechazada','proforma') AND tipo_documento <> 'proforma'"
_IMPAGADAS = ("vencida", "impagada", "reclamada", "judicial")
# Factor de normalización a MENSUAL para el MRR.
_FACTOR_MES = {"diaria": 30.0, "semanal": 4.333, "mensual": 1.0,
               "trimestral": 1 / 3, "semestral": 1 / 6, "anual": 1 / 12}


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def _scalar(cur):
    r = cur.fetchone()
    if not r:
        return 0.0
    return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)


def facturacion(desde=None, hasta=None, id_empresa=None) -> dict:
    """Total facturado + nº documentos + ticket medio del período (facturas válidas)."""
    id_empresa = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    cond, params = [f"id_empresa=%s AND {_VALIDAS}"], [id_empresa]
    if desde:
        cond.append("fecha_emision>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha_emision<=%s"); params.append(hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COALESCE(SUM(total),0), COUNT(*) FROM facturas_cliente "
                        f"WHERE {' AND '.join(cond)}", params)
            r = cur.fetchone()
            tot = float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
            n = int((r[1] if not isinstance(r, dict) else list(r.values())[1]) or 0)
        return {"facturacion": round(tot, 2), "documentos": n,
                "ticket_medio": round(tot / n, 2) if n else 0.0}
    except Exception as e:
        logger.error("analitica.facturacion: %s", e); return {"facturacion": 0, "documentos": 0}


def por_periodo(agrupacion="mes", desde=None, hasta=None, id_empresa=None) -> list:
    """Serie temporal de facturación. agrupacion: 'dia' | 'mes' | 'anio'."""
    id_empresa = _emp(id_empresa)
    fmt = {"dia": "%%Y-%%m-%%d", "mes": "%%Y-%%m", "anio": "%%Y"}.get(agrupacion, "%%Y-%%m")
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    cond, params = [f"id_empresa=%s AND {_VALIDAS}"], [id_empresa]
    if desde:
        cond.append("fecha_emision>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha_emision<=%s"); params.append(hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT DATE_FORMAT(fecha_emision,'{fmt}') p, COALESCE(SUM(total),0) t, "
                        f"COUNT(*) n FROM facturas_cliente WHERE {' AND '.join(cond)} "
                        f"GROUP BY p ORDER BY p", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("analitica.por_periodo: %s", e); return []


def ranking(dimension="cliente", desde=None, hasta=None, limite=20, id_empresa=None) -> list:
    """Facturación por 'cliente' o 'tienda'."""
    id_empresa = _emp(id_empresa)
    col = "id_tienda" if dimension == "tienda" else "id_cliente"
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    cond, params = [f"id_empresa=%s AND {_VALIDAS}"], [id_empresa]
    if desde:
        cond.append("fecha_emision>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha_emision<=%s"); params.append(hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {col} dim, COALESCE(SUM(total),0) t, COUNT(*) n "
                        f"FROM facturas_cliente WHERE {' AND '.join(cond)} "
                        f"GROUP BY {col} ORDER BY t DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("analitica.ranking: %s", e); return []


def recurrente_mrr_arr(id_empresa=None) -> dict:
    """MRR (ingreso recurrente mensual) y ARR (anual) a partir de las suscripciones activas."""
    id_empresa = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    mrr = 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT precio, frecuencia FROM cliente_suscripciones "
                        "WHERE id_empresa=%s AND estado='activa'", (id_empresa,))
            for r in cur.fetchall():
                precio = float((r[0] if not isinstance(r, dict) else r["precio"]) or 0)
                frec = (r[1] if not isinstance(r, dict) else r["frecuencia"]) or "mensual"
                mrr += precio * _FACTOR_MES.get(frec, 1.0)
    except Exception as e:
        logger.error("analitica.mrr: %s", e)
    mrr = round(mrr, 2)
    return {"mrr": mrr, "arr": round(mrr * 12, 2)}


def impagos(id_empresa=None) -> dict:
    """Impagos y morosidad: nº y € de facturas en estado vencida/impagada/reclamada/judicial."""
    id_empresa = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    marks = ",".join(["%s"] * len(_IMPAGADAS))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), COALESCE(SUM(total-COALESCE(cobrado,0)),0) "
                        f"FROM facturas_cliente WHERE id_empresa=%s AND estado IN ({marks})",
                        (id_empresa, *_IMPAGADAS))
            r = cur.fetchone()
            n = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
            pend = float((r[1] if not isinstance(r, dict) else list(r.values())[1]) or 0)
            cur.execute(f"SELECT COALESCE(SUM(total),0) FROM facturas_cliente "
                        f"WHERE id_empresa=%s AND {_VALIDAS}", (id_empresa,))
            facturado = _scalar(cur)
        tasa = round(pend / facturado * 100, 2) if facturado else 0.0
        return {"impagadas": n, "pendiente_cobro": round(pend, 2), "morosidad_pct": tasa}
    except Exception as e:
        logger.error("analitica.impagos: %s", e); return {"impagadas": 0, "pendiente_cobro": 0}


def resumen(id_empresa=None) -> dict:
    """Cuadro resumen para dashboards (reutilizable por el BI)."""
    return {"facturacion_total": facturacion(id_empresa=id_empresa),
            "recurrente": recurrente_mrr_arr(id_empresa),
            "impagos": impagos(id_empresa)}
