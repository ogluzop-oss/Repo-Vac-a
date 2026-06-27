"""
FASE H — Benchmarking interno. Rankings sobre el DW por tienda/almacen/empresa/periodo y, vía
modulos, por empleado/cliente/producto. Devuelve posiciones + percentil. Multiempresa.
"""

import logging
from src.services.bi_corp import olap
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.benchmarking")
_DIM_OK = ("id_tienda", "id_almacen", "id_empresa", "periodo")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def ranking(dimension, metrica, *, periodo=None, descendente=True, id_empresa=None, consolidado=False) -> list:
    """Ranking de la dimension por metrica. dimension in tienda/almacen/empresa/periodo."""
    if dimension not in _DIM_OK:
        raise ValueError(f"dimension invalida: {dimension}")
    filtros = {"metrica": metrica}
    if periodo:
        filtros["periodo"] = periodo
    filas = olap.cubo(dimensiones=(dimension,), filtros=filtros, agregacion="sum",
                      id_empresa=_emp(id_empresa), consolidado=consolidado)
    filas = [{"clave": f[dimension], "valor": round(float(f["valor"]), 2)} for f in filas]
    filas.sort(key=lambda x: x["valor"], reverse=descendente)
    n = len(filas)
    for i, f in enumerate(filas):
        f["posicion"] = i + 1
        f["percentil"] = round((n - i) * 100 / n, 1) if n else 0
    return filas


def ranking_empleados(metrica="productividad", *, id_empresa=None, limite=50) -> list:
    """Benchmarking de empleados (reutiliza RRHH si expone metricas; si no, vacio)."""
    eid = _emp(id_empresa)
    try:
        from src.rrhh.db import empleados
        if hasattr(empleados, "ranking_productividad"):
            return empleados.ranking_productividad(id_empresa=eid, limite=limite)
    except Exception as e:
        logger.debug("ranking_empleados: %s", e)
    return []


def ranking_clientes(*, id_empresa=None, limite=50) -> list:
    """Top clientes por facturacion (reutiliza ventas)."""
    eid = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT cliente_id, COALESCE(SUM(total),0) t FROM ventas WHERE id_empresa=%s "
                        "AND cliente_id IS NOT NULL GROUP BY cliente_id ORDER BY t DESC LIMIT %s",
                        (eid, int(limite)))
            return [{"id_cliente": (r[0] if not isinstance(r, dict) else list(r.values())[0]),
                     "facturacion": round(float(r[1] if not isinstance(r, dict) else list(r.values())[1]), 2),
                     "posicion": i + 1} for i, r in enumerate(cur.fetchall())]
    except Exception as e:
        logger.error("ranking_clientes: %s", e)
        return []


def ranking_productos(*, id_empresa=None, limite=50) -> list:
    eid = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_articulo, COALESCE(SUM(cantidad),0) c FROM movimientos_stock "
                        "WHERE id_empresa=%s AND tipo_movimiento='SALIDA_VENTA' GROUP BY codigo_articulo "
                        "ORDER BY c DESC LIMIT %s", (eid, int(limite)))
            return [{"articulo": (r[0] if not isinstance(r, dict) else list(r.values())[0]),
                     "unidades": float(r[1] if not isinstance(r, dict) else list(r.values())[1]),
                     "posicion": i + 1} for i, r in enumerate(cur.fetchall())]
    except Exception as e:
        logger.error("ranking_productos: %s", e)
        return []
