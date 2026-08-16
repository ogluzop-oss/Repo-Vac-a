"""Scorecard del proveedor (visible para empresa y proveedor).

REUTILIZA la evaluación existente (`db.compras.calcular_kpis_proveedor`, sobre incidencias/rechazos/
devoluciones/recepciones) y la ENRIQUECE con métricas del portal (estados de pedido reportados y
ofertas RFQ). No recalcula KPIs por su cuenta.
"""

from ._common import _conn, _emp, _filas, logger


def scorecard(id_proveedor, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    base = {"valoracion_global": 0.0, "incidencias": 0, "rechazos": 0, "devoluciones": 0,
            "pedidos_recibidos": 0}
    try:
        from src.db import compras as C
        k = C.calcular_kpis_proveedor(id_proveedor, emp) or {}
        base.update({kk: k.get(kk, base.get(kk)) for kk in base})
    except Exception as e:
        logger.debug("scorecard kpis: %s", e)
    # Métricas del portal: reparto de estados reportados por el proveedor.
    portal = {"aceptados": 0, "en_reparto": 0, "no_disponibles": 0, "ofertas_rfq": 0}
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT estado_proveedor, COUNT(*) AS n FROM portal_pedido_estado "
                        "WHERE id_empresa=%s AND id_proveedor=%s GROUP BY estado_proveedor",
                        (emp, id_proveedor))
            for r in _filas(cur):
                est = r["estado_proveedor"]
                if est == "aceptado":
                    portal["aceptados"] = int(r["n"])
                elif est == "en_reparto":
                    portal["en_reparto"] = int(r["n"])
                elif est == "no_disponible":
                    portal["no_disponibles"] = int(r["n"])
            cur.execute("SELECT COUNT(*) AS n FROM portal_rfq_ofertas "
                        "WHERE id_empresa=%s AND id_proveedor=%s", (emp, id_proveedor))
            r = _filas(cur)
            portal["ofertas_rfq"] = int(r[0]["n"]) if r else 0
    except Exception as e:
        logger.debug("scorecard portal: %s", e)
    base["portal"] = portal
    return base
