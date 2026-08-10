"""
Routing (Fase IV · Bloque 3). Tabla de rutas lógicas → servicio, sobre el Service Registry. Es la
abstracción que un futuro API Gateway / Load Balancer usará para enrutar (REST, GraphQL o
microservicios) sin conocer su ubicación física. Incluye una abstracción de balanceo (round-robin)
preparada para múltiples instancias del mismo servicio.
"""

from __future__ import annotations

import itertools
import threading

from src.platform import registry

_LOCK = threading.RLock()
_RR: dict = {}     # nombre_servicio -> ciclo round-robin de instancias (preparado)


def tabla() -> list:
    """Rutas declaradas por los servicios registrados: [(prefijo_ruta, servicio, transportes)]."""
    filas = []
    for c in registry.listar():
        for r in (c.rutas or ()):
            filas.append({"ruta": r, "servicio": c.nombre, "transportes": list(c.transportes)})
    return filas


def resolver(ruta, transporte=None):
    """Servicio (ServiceContract) que atiende `ruta` (prefijo más específico). None si ninguno."""
    candidatos = []
    for c in registry.listar():
        if transporte and transporte not in (c.transportes or ()):
            continue
        for r in (c.rutas or ()):
            if str(ruta).startswith(r):
                candidatos.append((len(r), c))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)   # prefijo más largo = más específico
    return candidatos[0][1]


def instancia(nombre, instancias=None):
    """Abstracción de balanceo: elige una instancia (round-robin). Hoy 1 instancia en proceso."""
    instancias = instancias or [nombre]
    with _LOCK:
        ciclo = _RR.get(nombre)
        if ciclo is None or getattr(ciclo, "_n", None) != len(instancias):
            ciclo = itertools.cycle(instancias)
            ciclo._n = len(instancias)   # type: ignore[attr-defined]
            _RR[nombre] = ciclo
        return next(ciclo)


__all__ = ["tabla", "resolver", "instancia"]
