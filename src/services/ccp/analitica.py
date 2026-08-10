"""
Communication Analytics (CCP Fase II · B5) — KPIs de comunicaciones.

Agrega métricas sobre `ccp_comunicaciones` + `ccp_cola` (nº comunicaciones, enviados/errores/
reintentos, por canal/estado/contexto/usuario) y complementa la telemetría Prometheus ya emitida en el
envío. Multiempresa. API-First (sin PyQt).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.analitica")

_DIMENSIONES = {"canal", "estado", "contexto", "usuario"}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _grupo(cur, id_empresa, campo, desde, hasta) -> dict:
    q = f"SELECT {campo} AS k, COUNT(*) AS n FROM ccp_comunicaciones WHERE id_empresa=%s"
    p = [id_empresa]
    if desde:
        q += " AND creado>=%s"; p.append(desde)
    if hasta:
        q += " AND creado<=%s"; p.append(hasta)
    q += f" GROUP BY {campo}"
    cur.execute(q, p)
    return {(r["k"] or "—"): int(r["n"]) for r in _filas_a_dicts(cur, cur.fetchall())}


def resumen(id_empresa=None, *, desde=None, hasta=None) -> dict:
    """KPIs globales de comunicaciones de la empresa."""
    id_empresa = _emp(id_empresa)
    out = {"total": 0, "enviados": 0, "fallidos": 0, "no_operativos": 0, "por_canal": {},
           "por_estado": {}, "por_contexto": {}, "por_usuario": {}, "cola_pendiente": 0,
           "reintentos": 0}
    if not id_empresa:
        return out
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            out["por_canal"] = _grupo(cur, id_empresa, "canal", desde, hasta)
            out["por_estado"] = _grupo(cur, id_empresa, "estado", desde, hasta)
            out["por_contexto"] = _grupo(cur, id_empresa, "contexto", desde, hasta)
            out["por_usuario"] = _grupo(cur, id_empresa, "usuario", desde, hasta)
            out["total"] = sum(out["por_estado"].values())
            out["enviados"] = out["por_estado"].get("enviado", 0) + out["por_estado"].get("entregado", 0)
            out["fallidos"] = out["por_estado"].get("fallido", 0)
            out["no_operativos"] = out["por_estado"].get("no_operativo", 0)
            cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(intentos),0) AS r FROM ccp_cola WHERE "
                        "id_empresa=%s AND estado='pendiente'", (id_empresa,))
            r = _filas_a_dicts(cur, cur.fetchall())
            if r:
                out["cola_pendiente"] = int(r[0]["n"])
            cur.execute("SELECT COALESCE(SUM(intentos),0) AS r FROM ccp_cola WHERE id_empresa=%s",
                        (id_empresa,))
            r2 = _filas_a_dicts(cur, cur.fetchall())
            if r2:
                out["reintentos"] = int(r2[0]["r"])
    except Exception as e:
        logger.debug("resumen: %s", e)
    out["tasa_exito"] = round(100 * out["enviados"] / out["total"], 1) if out["total"] else 0.0
    return out


def por_dimension(id_empresa=None, dimension="canal", *, desde=None, hasta=None) -> dict:
    """Recuento de comunicaciones agrupado por una dimensión (canal/estado/contexto/usuario)."""
    id_empresa = _emp(id_empresa)
    if dimension not in _DIMENSIONES or not id_empresa:
        return {}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            return _grupo(cur, id_empresa, dimension, desde, hasta)
    except Exception as e:
        logger.debug("por_dimension: %s", e)
        return {}
