"""
Cloud · Load Balancing (Fase VI · Bloque 11) — ABSTRACCIÓN. Estrategias de balanceo entre nodos:
Round Robin, Least Connections, Region First y Sticky Sessions. NO implementa un balanceador real
(no abre puertos): elige un nodo del Node Registry según la estrategia. Preparación para el Gateway
distribuido.
"""

from __future__ import annotations

import threading

from src.platform.cloud import nodes

ROUND_ROBIN, LEAST_CONNECTIONS, REGION_FIRST, STICKY = (
    "round_robin", "least_connections", "region_first", "sticky")
ESTRATEGIAS = (ROUND_ROBIN, LEAST_CONNECTIONS, REGION_FIRST, STICKY)

_LOCK = threading.RLock()
_rr_idx = {"i": 0}
_sticky: dict = {}     # clave_sesion -> nombre_nodo


def elegir(estrategia=ROUND_ROBIN, *, region=None, clave_sesion=None):
    """Devuelve el nodo elegido (Nodo) o None si no hay nodos disponibles."""
    candidatos = nodes.disponibles()
    if region:
        preferidos = [n for n in candidatos if n.region == region]
        if estrategia == REGION_FIRST:
            candidatos = preferidos or candidatos
        elif preferidos:
            candidatos = preferidos
    if not candidatos:
        return None

    if estrategia == LEAST_CONNECTIONS:
        return min(candidatos, key=lambda n: (n.carga, n.latencia_ms))
    if estrategia == REGION_FIRST:
        return min(candidatos, key=lambda n: (n.latencia_ms, n.carga))
    if estrategia == STICKY and clave_sesion:
        with _LOCK:
            nombre = _sticky.get(clave_sesion)
            elegido = next((n for n in candidatos if n.nombre == nombre), None)
            if elegido is None:
                elegido = candidatos[0]
                _sticky[clave_sesion] = elegido.nombre
            return elegido
    # Round Robin (por defecto).
    with _LOCK:
        i = _rr_idx["i"] % len(candidatos)
        _rr_idx["i"] = (i + 1) % max(1, len(candidatos))
        return candidatos[i]


def reset():
    with _LOCK:
        _rr_idx["i"] = 0
        _sticky.clear()


__all__ = ["ROUND_ROBIN", "LEAST_CONNECTIONS", "REGION_FIRST", "STICKY", "ESTRATEGIAS",
           "elegir", "reset"]
