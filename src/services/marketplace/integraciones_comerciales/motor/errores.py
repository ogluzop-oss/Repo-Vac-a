"""
Motor · TIPOS DE ERROR canónicos (Fase WEB-13). Solo definiciones — en esta fase NO se lanza ningún error
real (no hay conexiones). Los adaptadores futuros usarán estos códigos para normalizar sus fallos.
"""

import enum


class CodigoError(enum.Enum):
    AUTH_ERROR = "AUTH_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    API_ERROR = "API_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    INVALID_DOMAIN = "INVALID_DOMAIN"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"


CODIGOS = tuple(c.value for c in CodigoError)


class IntegracionError(Exception):
    """Error normalizado de integración. Se DEFINE aquí; no se lanza en esta fase (arquitectura)."""

    def __init__(self, codigo: CodigoError, mensaje: str = "", *, plataforma=None, detalle=None):
        self.codigo = codigo
        self.plataforma = plataforma
        self.detalle = detalle
        super().__init__(f"[{getattr(codigo, 'value', codigo)}] {mensaje}")

    def to_dict(self) -> dict:
        return {"codigo": getattr(self.codigo, "value", self.codigo), "mensaje": str(self),
                "plataforma": self.plataforma, "detalle": self.detalle}
