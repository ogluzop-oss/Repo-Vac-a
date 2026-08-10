"""
Cloud · Node Registry (Fase VI · Bloque 11). Registro EN MEMORIA de los NODOS FÍSICOS del clúster
(distinto del Service Registry, que registra servicios lógicos). Cada nodo publica nombre, versión,
dirección, región, estado de salud, latencia y carga. Preparación para despliegue distribuido: hoy
un solo nodo en proceso; mañana N nodos con el MISMO contrato. Sin red ni BD.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Estados de health check de un nodo.
ALIVE, READY, DEGRADED, MAINTENANCE = "alive", "ready", "degraded", "maintenance"
ESTADOS = (ALIVE, READY, DEGRADED, MAINTENANCE)

_LOCK = threading.RLock()
_NODOS: dict = {}


@dataclass
class Nodo:
    nombre: str
    version: str = "1.0.0"
    direccion: str = "127.0.0.1"
    region: str = "eu"
    estado: str = READY
    latencia_ms: float = 0.0
    carga: float = 0.0            # 0..1 (utilización)
    registrado: float = field(default_factory=time.time)
    hb: float = field(default_factory=time.time)

    def as_dict(self):
        return {"nombre": self.nombre, "version": self.version, "direccion": self.direccion,
                "region": self.region, "estado": self.estado, "latencia_ms": self.latencia_ms,
                "carga": self.carga, "ultimo_heartbeat": self.hb}


def registrar(nombre, *, version="1.0.0", direccion="127.0.0.1", region="eu", estado=READY,
              latencia_ms=0.0, carga=0.0) -> bool:
    if not nombre or estado not in ESTADOS:
        return False
    with _LOCK:
        prev = _NODOS.get(nombre)
        n = Nodo(nombre, version, direccion, region, estado, latencia_ms, carga)
        if prev:
            n.registrado = prev.registrado
        _NODOS[nombre] = n
    return True


def actualizar(nombre, *, estado=None, latencia_ms=None, carga=None) -> bool:
    with _LOCK:
        n = _NODOS.get(nombre)
        if not n:
            return False
        if estado is not None and estado in ESTADOS:
            n.estado = estado
        if latencia_ms is not None:
            n.latencia_ms = latencia_ms
        if carga is not None:
            n.carga = carga
        n.hb = time.time()
        return True


def latido(nombre) -> bool:
    with _LOCK:
        n = _NODOS.get(nombre)
        if not n:
            return False
        n.hb = time.time()
        return True


def dar_de_baja(nombre) -> bool:
    with _LOCK:
        return _NODOS.pop(nombre, None) is not None


def obtener(nombre) -> Nodo | None:
    with _LOCK:
        return _NODOS.get(nombre)


def listar(*, region=None, estado=None) -> list:
    with _LOCK:
        nodos = list(_NODOS.values())
    if region:
        nodos = [n for n in nodos if n.region == region]
    if estado:
        nodos = [n for n in nodos if n.estado == estado]
    return nodos


def disponibles() -> list:
    """Nodos que pueden atender tráfico (alive/ready)."""
    return [n for n in listar() if n.estado in (ALIVE, READY)]


def limpiar():
    with _LOCK:
        _NODOS.clear()


__all__ = ["ALIVE", "READY", "DEGRADED", "MAINTENANCE", "ESTADOS", "Nodo", "registrar",
           "actualizar", "latido", "dar_de_baja", "obtener", "listar", "disponibles", "limpiar"]
