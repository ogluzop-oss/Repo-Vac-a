"""
Data Lake · Orquestación (Fase V · Bloque 6). Separa ERP operativo → Data Lake → BI → IA REUTILIZANDO
el Data Warehouse existente (`services.bi_corp.dw`) como capa de hechos: NO crea un segundo almacén.
Orquesta Extracción/Transformación/Carga, snapshots e históricos, apoyándose en Scheduler y Event Bus.
Multiempresa.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("datalake.lake")

# Dominios del lago (los mismos del DW corporativo; fuente única de hechos).
DOMINIOS = ("ventas", "compras", "stock", "rrhh", "produccion", "calidad", "finanzas",
            "logistica", "ccp", "workflow", "api", "usuarios", "empresas")


def ejecutar_etl(*, dominios=None, granularidad="mensual", fecha=None, id_empresa=None) -> dict:
    """ETL del lago: delega en el DW corporativo (extracción→transformación→carga de hechos)."""
    try:
        from src.services.bi_corp import dw
        return dw.ejecutar_etl(dominios=dominios or list(DOMINIOS), granularidad=granularidad,
                               fecha=fecha, id_empresa=id_empresa)
    except Exception as e:
        logger.error("ejecutar_etl: %s", e)
        return {"ok": False, "error": str(e)}


def consultar(*, dominio=None, metrica=None, granularidad=None, periodo=None, id_empresa=None):
    """Consulta de hechos del lago (delega en el DW; nunca SQL propio)."""
    try:
        from src.services.bi_corp import dw
        return dw.consultar(dominio=dominio, metrica=metrica, granularidad=granularidad,
                            periodo=periodo, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("consultar: %s", e)
        return []


def snapshot(*, id_empresa=None, granularidad="mensual"):
    """Snapshot histórico del lago (reutiliza los snapshots de BI si están disponibles)."""
    try:
        from src.services.bi import snapshots
        if hasattr(snapshots, "generar"):
            return snapshots.generar(id_empresa=id_empresa)
    except Exception:
        pass
    # Degradable: un snapshot es una ejecución ETL con la granularidad indicada.
    return ejecutar_etl(granularidad=granularidad, id_empresa=id_empresa)


def registrar_jobs(id_empresa=None):
    """Registra los jobs de ETL del lago en el Scheduler (reutiliza el registro del DW)."""
    try:
        from src.services.bi_corp import dw
        if hasattr(dw, "registrar_jobs_dw"):
            return dw.registrar_jobs_dw(id_empresa)
    except Exception:
        pass
    return None


def descriptor() -> dict:
    return {"dominios": list(DOMINIOS), "almacen": "bi_corp.dw (reutilizado)",
            "capas": ["extraccion", "transformacion", "carga", "modelado", "snapshots",
                      "historicos", "kpis"],
            "integracion": ["observabilidad", "eventbus", "scheduler", "analytics"]}


__all__ = ["DOMINIOS", "ejecutar_etl", "consultar", "snapshot", "registrar_jobs", "descriptor"]
