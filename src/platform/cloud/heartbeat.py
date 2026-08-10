"""
Cloud · Heartbeat de nodos (Fase VI · Bloque 11). Late y detecta nodos «stale» del clúster. Reutiliza
el registro de nodos (`nodes`). Preparado para que cada nodo remoto emita su latido periódico.
"""

from __future__ import annotations

import time

from src.platform.cloud import nodes

UMBRAL_STALE_S = 90.0


def latir(nombre) -> bool:
    return nodes.latido(nombre)


def antiguedad(nombre) -> float | None:
    n = nodes.obtener(nombre)
    return (time.time() - n.hb) if n else None


def vivo(nombre, umbral=UMBRAL_STALE_S) -> bool:
    a = antiguedad(nombre)
    return a is not None and a <= umbral


def stale(umbral=UMBRAL_STALE_S) -> list:
    return [n.nombre for n in nodes.listar() if not vivo(n.nombre, umbral)]


__all__ = ["UMBRAL_STALE_S", "latir", "antiguedad", "vivo", "stale"]
