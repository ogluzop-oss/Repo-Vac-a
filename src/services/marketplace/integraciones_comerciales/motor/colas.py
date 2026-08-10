"""
Motor · SISTEMA DE COLAS (Fase WEB-13). Contrato ÚNICO de cola de trabajos para que el código de negocio no
dependa del backend. `ColaLocal` es una cola en memoria (utilidad, sin infraestructura externa); Redis/SQS/
RabbitMQ quedan PREPARADOS (elevan `NotImplementedError` — sin conexión real). Cambiar de backend NO requiere
tocar el negocio.
"""

import collections
from abc import ABC, abstractmethod


class ColaTrabajos(ABC):
    """Contrato de cola de trabajos. Backends intercambiables (local/redis/sqs/rabbitmq)."""

    backend = "base"

    @abstractmethod
    def encolar(self, trabajo: dict) -> None: ...

    @abstractmethod
    def desencolar(self) -> dict | None: ...

    @abstractmethod
    def tamano(self) -> int: ...

    def descriptor(self) -> dict:
        return {"backend": self.backend, "disponible": isinstance(self, ColaLocal)}


class ColaLocal(ColaTrabajos):
    """Cola en memoria (utilidad para desarrollo/tests). No usa infraestructura externa."""
    backend = "local"

    def __init__(self, **_cfg):
        self._q = collections.deque()

    def encolar(self, trabajo: dict) -> None:
        self._q.append(trabajo)

    def desencolar(self) -> dict | None:
        return self._q.popleft() if self._q else None

    def tamano(self) -> int:
        return len(self._q)


class _ColaRemotaPreparada(ColaTrabajos):
    """Base de colas remotas PREPARADAS: guardan la referencia de configuración (nunca secretos) y elevan
    `NotImplementedError` hasta que se implemente el backend real en fases posteriores."""

    def __init__(self, *, config_ref=None, **_cfg):
        self.config_ref = config_ref     # nombre/refencia (Secret Manager), nunca credenciales en claro

    def encolar(self, trabajo: dict) -> None:
        raise NotImplementedError(f"backend '{self.backend}' preparado (sin implementación real)")

    def desencolar(self) -> dict | None:
        raise NotImplementedError(f"backend '{self.backend}' preparado (sin implementación real)")

    def tamano(self) -> int:
        raise NotImplementedError(f"backend '{self.backend}' preparado (sin implementación real)")


class ColaRedis(_ColaRemotaPreparada):
    backend = "redis"


class ColaSQS(_ColaRemotaPreparada):
    backend = "sqs"


class ColaRabbitMQ(_ColaRemotaPreparada):
    backend = "rabbitmq"


BACKENDS = {"local": ColaLocal, "redis": ColaRedis, "sqs": ColaSQS, "rabbitmq": ColaRabbitMQ}


def cola(backend: str = "local", **cfg) -> ColaTrabajos:
    """Factoría de cola por backend (dirigida por registro, sin ramificar por backend)."""
    cls = BACKENDS.get((backend or "local").lower())
    if cls is None:
        raise ValueError(f"backend de cola no reconocido: {backend}")
    return cls(**cfg)
