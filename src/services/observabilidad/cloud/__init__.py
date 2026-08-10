"""
Cloud Observability (Fase VI · Bloque 12) — fachada. EXTIENDE la Observabilidad Enterprise hacia
despliegues distribuidos SIN modificarla: métricas cloud (nodos/regiones/clústeres/…), logging
centralizado (ELK/OpenSearch/Loki preparado), tracing distribuido (Trace/Span/Correlation/
Communication/Workflow ID) y alertas cloud, todo agregado en un Cloud Dashboard.

    from src.services.observabilidad import cloud as obs_cloud
    obs_cloud.dashboard_cloud.panel()
    obs_cloud.tracing.nuevo_trace()
"""

from src.services.observabilidad.cloud import (  # noqa: F401
    alertas_cloud, dashboard_cloud, log_collector, metricas_cloud,
)
from src.services.observabilidad.cloud import distributed_tracing as tracing  # noqa: F401

__all__ = ["alertas_cloud", "dashboard_cloud", "log_collector", "metricas_cloud", "tracing"]
