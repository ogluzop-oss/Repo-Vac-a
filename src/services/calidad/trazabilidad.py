"""
CAL-E — Trazabilidad de calidad. NO crea trazabilidad paralela: reutiliza lotes/movimientos_stock
(db.lotes) y agrega la dimension calidad (inspecciones/NC) + OF de origen. Soporte opcional de
numero de serie via el campo `lote` (un lote de 1 unidad = serie).
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.trazabilidad")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _filas(cur):
    return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))) for r in cur.fetchall()]


def trazabilidad_lote(id_lote, *, id_empresa=None) -> dict:
    """Une la trazabilidad de stock (kardex) del lote con su calidad (inspecciones + NC)."""
    eid = _emp(id_empresa)
    out = {"movimientos": [], "inspecciones": [], "no_conformidades": [], "of_origen": None}
    try:
        from src.db import lotes
        out["movimientos"] = lotes.trazabilidad_lote(id_lote, id_empresa=eid)
    except Exception as e:
        logger.debug("trazabilidad stock: %s", e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM inspecciones WHERE id_empresa=%s AND id_lote=%s", (eid, id_lote))
            out["inspecciones"] = _filas(cur)
            cur.execute("SELECT * FROM no_conformidades WHERE id_empresa=%s AND id_lote=%s", (eid, id_lote))
            out["no_conformidades"] = _filas(cur)
            # OF de origen: lote producido por una OF cuyo lote_destino coincide.
            cur.execute("SELECT o.id, o.codigo FROM ordenes_fabricacion o JOIN lotes l ON l.lote=o.lote_destino "
                        "AND l.id_empresa=o.id_empresa WHERE l.id=%s LIMIT 1", (id_lote,))
            r = cur.fetchone()
            out["of_origen"] = (r if isinstance(r, dict) else {"id": r[0], "codigo": r[1]}) if r else None
    except Exception as e:
        logger.debug("trazabilidad calidad: %s", e)
    return out


def trazabilidad_articulo(codigo, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    out = {"movimientos": [], "inspecciones": [], "no_conformidades": []}
    try:
        from src.db import lotes
        out["movimientos"] = lotes.trazabilidad_articulo(codigo, id_empresa=eid)
    except Exception:
        pass
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM inspecciones WHERE id_empresa=%s AND articulo=%s ORDER BY fecha DESC LIMIT 200",
                        (eid, codigo))
            out["inspecciones"] = _filas(cur)
            cur.execute("SELECT * FROM no_conformidades WHERE id_empresa=%s AND articulo=%s "
                        "ORDER BY fecha_apertura DESC LIMIT 200", (eid, codigo))
            out["no_conformidades"] = _filas(cur)
    except Exception as e:
        logger.debug("trazabilidad articulo calidad: %s", e)
    return out
