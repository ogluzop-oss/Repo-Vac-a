"""
Cloud Distributed Architecture (Fase VI · Bloque 11) — fachada.

Prepara la infraestructura para MÚLTIPLES NODOS FÍSICOS sin dividir el ERP: Node Registry, heartbeat
de nodos, clústeres, service discovery distribuido (sobre el Service Registry lógico), load balancing
(abstracción), failover (preparado) y storage abstraction (Local/S3/Azure/GCS/MinIO). Todo en proceso
hoy; distribuible mañana con el MISMO contrato. Reutiliza `src.platform` (registry/discovery/health).

    from src.platform import cloud
    cloud.nodes.registrar("node-eu-1", region="eu")
    cloud.routing.elegir(cloud.routing.REGION_FIRST, region="eu")
    cloud.discovery.topologia()
"""

from src.platform.cloud import (cluster, discovery, failover, heartbeat, nodes, routing,  # noqa: F401
                                storage)

CLOUD_VERSION = "1.0.0"

# Regiones soportadas (alineadas con el Global SaaS Platform, Bloque 13).
REGIONES = ("eu", "am", "as", "af", "oc")


def bootstrap_local() -> bool:
    """Registra un nodo local (el proceso actual) para que la topología no esté vacía en dev."""
    return nodes.registrar("node-local", region="eu", estado=nodes.READY)


def descriptor() -> dict:
    return {"version": CLOUD_VERSION, "regiones": list(REGIONES),
            "load_balancing": list(routing.ESTRATEGIAS),
            "storage": list(storage.PROVEEDORES),
            "failover": [failover.PRIMARY, failover.SECONDARY, failover.RECOVERY],
            "health_states": list(nodes.ESTADOS)}


__all__ = ["CLOUD_VERSION", "REGIONES", "cluster", "discovery", "failover", "heartbeat", "nodes",
           "routing", "storage", "bootstrap_local", "descriptor"]
