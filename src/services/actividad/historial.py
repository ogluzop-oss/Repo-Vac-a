"""
Historial completo de un evento (Fase 3, SUBFASE 3.9).

Permite reconstruir toda la vida del cambio: quien lo hizo, cuando, desde que terminal,
cuando llego a cada destino y cuando se aplico (confirmacion). Une eventos + historial de
evento (Fase 1) + distribucion + confirmaciones (Fase 2).
"""

import logging

logger = logging.getLogger("actividad.historial")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _dicts(cur):
    try:
        from src.db.conexion import _filas_a_dicts
        return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def detalle(id_evento, id_empresa=None) -> dict:
    """Traza completa: evento + ciclo de vida + distribucion por terminal + confirmaciones."""
    emp = _emp(id_empresa)
    res = {"evento": None, "ciclo_vida": [], "distribucion": [], "confirmaciones": []}
    try:
        from src.services import eventos as _EV
        res["evento"] = _EV.obtener(id_evento, id_empresa=emp)
        res["ciclo_vida"] = _EV.historial(id_evento, id_empresa=emp)
    except Exception as e:
        logger.debug("detalle evento: %s", e)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, destino, tipo_destino, destino_tienda, estado, "
                        "fecha_envio, fecha_confirmacion, reintentos, error "
                        "FROM distribucion_pendiente WHERE id_empresa=%s AND id_evento=%s "
                        "ORDER BY id", (emp, id_evento))
            res["distribucion"] = _dicts(cur)
            cur.execute("SELECT id_distribucion, terminal, id_tienda, estado, detalle, fecha "
                        "FROM distribucion_confirmaciones WHERE id_empresa=%s AND id_evento=%s "
                        "ORDER BY id", (emp, id_evento))
            res["confirmaciones"] = _dicts(cur)
    except Exception as e:
        logger.error("detalle distribucion: %s", e)
    return res
