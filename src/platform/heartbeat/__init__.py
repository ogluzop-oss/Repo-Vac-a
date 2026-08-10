"""
Heartbeat manager (Fase IV · Bloque 3). Registra el latido de cada servicio y detecta los que
quedan «stale» (sin latido reciente). Preparado para que, al distribuirse, cada microservicio
emita su heartbeat periódico. En proceso, se puede latir manualmente o al hacer health checks.
"""

from __future__ import annotations

import time

from src.platform import registry

# Umbral por defecto: un servicio se considera «stale» si no late en 90 s.
UMBRAL_STALE_S = 90.0


def latir(nombre) -> bool:
    """Marca un heartbeat del servicio en el registro."""
    return registry.latido(nombre)


def ultimo(nombre) -> float | None:
    e = registry.entrada(nombre)
    return e.get("hb") if e else None


def antiguedad(nombre) -> float | None:
    """Segundos desde el último heartbeat (None si no está registrado)."""
    hb = ultimo(nombre)
    return (time.time() - hb) if hb else None


def esta_vivo(nombre, umbral=UMBRAL_STALE_S) -> bool:
    a = antiguedad(nombre)
    return a is not None and a <= umbral


def stale(umbral=UMBRAL_STALE_S) -> list:
    """Lista de servicios sin latido reciente."""
    return [n for n in registry.nombres() if not esta_vivo(n, umbral)]


__all__ = ["UMBRAL_STALE_S", "latir", "ultimo", "antiguedad", "esta_vivo", "stale"]
