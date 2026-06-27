"""
FASE E — Cuadro de mando multiempresa. Consolida N empresas (1..1000+) desde el DW con filtros
(empresa/tienda/almacen/region/periodo). Escala porque agrega sobre dw_hechos (no transaccional).
"""

import logging
from src.services.bi_corp import olap
from src.db.conexion import obtener_conexion

logger = logging.getLogger("bi_corp.consolidacion")


def empresas_disponibles() -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT id_empresa FROM dw_hechos")
            return [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
    except Exception as e:
        logger.error("empresas_disponibles: %s", e)
        return []


def consolidar(metricas, *, empresas=None, periodo=None, id_tienda=None, id_almacen=None) -> dict:
    """Consolida una lista de metricas sobre las empresas indicadas (todas si None).
    Devuelve {metrica: {total, por_empresa:{id:valor}}}."""
    filtros_base = {}
    if periodo:
        filtros_base["periodo"] = periodo
    if id_tienda is not None:
        filtros_base["id_tienda"] = id_tienda
    if id_almacen is not None:
        filtros_base["id_almacen"] = id_almacen
    if empresas:
        filtros_base["id_empresa"] = list(empresas)
    out = {}
    for met in metricas:
        filtros = dict(filtros_base, metrica=met)
        # Agregado por empresa (consolidado = no filtra por tenant actual).
        filas = olap.cubo(dimensiones=("id_empresa",), filtros=filtros, agregacion="sum", consolidado=True)
        por_empresa = {f["id_empresa"]: round(float(f["valor"]), 2) for f in filas}
        out[met] = {"total": round(sum(por_empresa.values()), 2), "por_empresa": por_empresa,
                    "num_empresas": len(por_empresa)}
    return out


def ranking_empresas(metrica, *, periodo=None, descendente=True, limite=1000) -> list:
    """Ranking de empresas por una metrica (benchmarking entre empresas del grupo)."""
    filtros = {"metrica": metrica}
    if periodo:
        filtros["periodo"] = periodo
    filas = olap.cubo(dimensiones=("id_empresa",), filtros=filtros, agregacion="sum",
                      consolidado=True, limite=limite)
    filas.sort(key=lambda f: float(f["valor"]), reverse=descendente)
    return [{"id_empresa": f["id_empresa"], "valor": round(float(f["valor"]), 2),
             "posicion": i + 1} for i, f in enumerate(filas)]
