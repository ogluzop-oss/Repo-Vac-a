"""
Data Lake + Enterprise BI (Fase V · Bloque 6) — fachada.

Separa ERP operativo → Data Lake → BI → IA REUTILIZANDO el Data Warehouse corporativo
(`services.bi_corp.dw`) como capa de hechos: NO crea un segundo almacén ni un segundo motor de BI.
Orquesta ETL, snapshots, históricos y dashboards, apoyándose en Observabilidad, Event Bus, Scheduler
y Analytics existentes. Multiempresa.

    from src.services import datalake
    datalake.ejecutar_etl(granularidad="mensual", id_empresa=emp)
    datalake.dashboards.dashboard("ventas", id_empresa=emp)
"""

from src.services.datalake.lake import (  # noqa: F401
    DOMINIOS, ejecutar_etl, consultar, snapshot, registrar_jobs, descriptor,
)
from src.services.datalake import dashboards  # noqa: F401

__all__ = ["DOMINIOS", "ejecutar_etl", "consultar", "snapshot", "registrar_jobs", "descriptor",
           "dashboards"]
