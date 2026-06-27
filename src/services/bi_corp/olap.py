"""
FASE B — Modelo OLAP sobre dw_hechos. Cubos con agregacion por dimensiones (empresa/tienda/
almacen/dominio/metrica/periodo), operaciones drill-down/up, slice, dice y comparativa temporal.
Trabaja sobre la capa DW (no sobre transaccional).
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.olap")
DIMENSIONES = ("id_empresa", "id_tienda", "id_almacen", "dominio", "metrica", "periodo", "granularidad")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def cubo(*, dimensiones=("dominio", "metrica"), metrica=None, filtros=None, agregacion="sum",
         id_empresa=None, consolidado=False, limite=10000) -> list:
    """Agrega dw_hechos por las dimensiones indicadas. filtros: {col: valor|[valores]}.
    consolidado=True agrega sobre TODAS las empresas (no filtra por id_empresa)."""
    dims = [d for d in dimensiones if d in DIMENSIONES]
    if not dims:
        dims = ["dominio"]
    agg = {"sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN", "count": "COUNT"}.get(agregacion, "SUM")
    sel = ", ".join(dims)
    q = f"SELECT {sel}, {agg}(valor) AS valor, COUNT(*) AS n FROM dw_hechos WHERE 1=1"
    p = []
    if not consolidado:
        q += " AND id_empresa=%s"; p.append(_emp(id_empresa))
    if metrica:
        q += " AND metrica=%s"; p.append(metrica)
    for col, val in (filtros or {}).items():
        if col not in DIMENSIONES:
            continue
        if isinstance(val, (list, tuple)):
            q += f" AND {col} IN ({','.join(['%s'] * len(val))})"; p.extend(val)
        else:
            q += f" AND {col}=%s"; p.append(val)
    q += f" GROUP BY {sel} ORDER BY valor DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, (r if not isinstance(r, dict) else list(r.values())))) for r in cur.fetchall()]
    except Exception as e:
        logger.error("cubo: %s", e)
        return []


def drill_down(dimension_actual, *, metrica=None, filtros=None, id_empresa=None) -> list:
    """Baja un nivel de detalle: empresa -> tienda -> almacen; dominio -> metrica."""
    jerarquia = {"id_empresa": "id_tienda", "id_tienda": "id_almacen", "dominio": "metrica"}
    siguiente = jerarquia.get(dimension_actual, "metrica")
    return cubo(dimensiones=(dimension_actual, siguiente), metrica=metrica, filtros=filtros, id_empresa=id_empresa)


def drill_up(dimension_actual, *, metrica=None, filtros=None, id_empresa=None) -> list:
    """Sube un nivel (agrega): almacen -> tienda -> empresa; metrica -> dominio."""
    jerarquia = {"id_almacen": "id_tienda", "id_tienda": "id_empresa", "metrica": "dominio"}
    superior = jerarquia.get(dimension_actual, "dominio")
    return cubo(dimensiones=(superior,), metrica=metrica, filtros=filtros, id_empresa=id_empresa)


def slice_(dimension, valor, *, metrica=None, id_empresa=None) -> list:
    """Slice: fija una dimension a un valor y agrega por metrica."""
    return cubo(dimensiones=("metrica",), metrica=metrica, filtros={dimension: valor}, id_empresa=id_empresa)


def dice(filtros, *, dimensiones=("dominio", "metrica"), id_empresa=None) -> list:
    """Dice: subcubo con varios filtros simultaneos."""
    return cubo(dimensiones=dimensiones, filtros=filtros, id_empresa=id_empresa)


def comparativa_temporal(metrica, periodos, *, dominio=None, id_empresa=None) -> dict:
    """Compara una metrica entre periodos. Devuelve {periodo: valor} + variacion ult vs primero."""
    eid = _emp(id_empresa)
    filtros = {"metrica": metrica, "periodo": list(periodos)}
    if dominio:
        filtros["dominio"] = dominio
    filas = cubo(dimensiones=("periodo",), filtros=filtros, id_empresa=eid)
    serie = {f["periodo"]: float(f["valor"]) for f in filas}
    ordenados = [serie.get(p, 0.0) for p in periodos]
    variacion = None
    if len(ordenados) >= 2 and ordenados[0]:
        variacion = round((ordenados[-1] - ordenados[0]) * 100 / abs(ordenados[0]), 2)
    return {"metrica": metrica, "serie": serie, "variacion_pct": variacion}
