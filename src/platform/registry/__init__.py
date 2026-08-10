"""
Service Registry (Fase IV · Bloque 3). Registro EN MEMORIA de los servicios de la plataforma
(IOC, CCP, REST, GraphQL, Scheduler, Workflow, Rules, Observability, Marketplace, IA, BI…). Cada
servicio se registra con su `ServiceContract`. Es la fuente única para Discovery, Health, Routing
y el Gateway. Sin red ni BD: hoy en proceso, preparado para distribuirse mañana.
"""

from __future__ import annotations

import threading
import time

from src.platform.contracts import ServiceContract

_LOCK = threading.RLock()
_SERVICIOS: dict = {}          # nombre -> {"contrato": ServiceContract, "registrado": ts, "hb": ts}


def registrar(contrato: ServiceContract) -> bool:
    """Registra (o actualiza) un servicio por su contrato. Devuelve False si el contrato es inválido."""
    ok, _errores = contrato.validar()
    if not ok:
        return False
    with _LOCK:
        prev = _SERVICIOS.get(contrato.nombre)
        _SERVICIOS[contrato.nombre] = {
            "contrato": contrato,
            "registrado": prev["registrado"] if prev else time.time(),
            "hb": time.time(),
        }
    return True


def dar_de_baja(nombre) -> bool:
    with _LOCK:
        return _SERVICIOS.pop(nombre, None) is not None


def obtener(nombre) -> ServiceContract | None:
    with _LOCK:
        e = _SERVICIOS.get(nombre)
        return e["contrato"] if e else None


def entrada(nombre) -> dict | None:
    with _LOCK:
        e = _SERVICIOS.get(nombre)
        return dict(e) if e else None


def listar() -> list:
    with _LOCK:
        return [e["contrato"] for e in _SERVICIOS.values()]


def nombres() -> list:
    with _LOCK:
        return list(_SERVICIOS.keys())


def latido(nombre) -> bool:
    """Marca un heartbeat del servicio (lo llama el heartbeat manager)."""
    with _LOCK:
        e = _SERVICIOS.get(nombre)
        if not e:
            return False
        e["hb"] = time.time()
        return True


def limpiar():
    """Reinicia el registro (tests)."""
    with _LOCK:
        _SERVICIOS.clear()


__all__ = ["registrar", "dar_de_baja", "obtener", "entrada", "listar", "nombres", "latido", "limpiar"]
