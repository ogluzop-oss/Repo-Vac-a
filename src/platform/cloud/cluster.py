"""
Cloud · Cluster (Fase VI · Bloque 11). Agrupa nodos en clústeres (por región u objetivo) y agrega su
salud. Reutiliza el Node Registry. Preparación: describe la topología física sin desplegarla.
"""

from __future__ import annotations

from src.platform.cloud import heartbeat, nodes

_CLUSTERS: dict = {}     # nombre_cluster -> {"region": r, "nodos": set()}


def crear_cluster(nombre, *, region="eu") -> bool:
    _CLUSTERS.setdefault(nombre, {"region": region, "nodos": set()})["region"] = region
    return True


def asignar_nodo(cluster, nombre_nodo) -> bool:
    if cluster not in _CLUSTERS or not nodes.obtener(nombre_nodo):
        return False
    _CLUSTERS[cluster]["nodos"].add(nombre_nodo)
    return True


def salud_cluster(cluster) -> dict:
    c = _CLUSTERS.get(cluster)
    if not c:
        return {"cluster": cluster, "estado": "desconocido"}
    ns = [nodes.obtener(n) for n in c["nodos"] if nodes.obtener(n)]
    vivos = [n for n in ns if n.estado in (nodes.ALIVE, nodes.READY) and heartbeat.vivo(n.nombre)]
    if not ns:
        estado = "vacio"
    elif len(vivos) == len(ns):
        estado = "ok"
    elif vivos:
        estado = "degraded"
    else:
        estado = "down"
    return {"cluster": cluster, "region": c["region"], "estado": estado,
            "nodos": len(ns), "vivos": len(vivos),
            "carga_media": round(sum(n.carga for n in ns) / len(ns), 3) if ns else 0.0}


def listar_clusters() -> list:
    return [salud_cluster(c) for c in _CLUSTERS]


def limpiar():
    _CLUSTERS.clear()


__all__ = ["crear_cluster", "asignar_nodo", "salud_cluster", "listar_clusters", "limpiar"]
