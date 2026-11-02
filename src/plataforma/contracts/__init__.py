"""
Contratos de plataforma (Fase IV · Bloque 3 · Preparación para microservicios).

Define las INTERFACES COMUNES que todo subsistema (actual o futuro microservicio) comparte:
Request / Response / Error / Event / AuthContext / Tracing / HealthStatus / Version y el
descriptor de servicio `ServiceContract`. Son estructuras neutrales (sin red, sin framework):
hoy los servicios viven en proceso; mañana el MISMO contrato permite exponerlos como microservicios
sin rediseñar nada. NO accede a la BD ni contiene lógica de negocio.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ── Comunicación soportada / preparada ──────────────────────────────────────────
TRANSPORTES = ("rest", "graphql", "eventbus", "rpc", "broker")   # rpc/broker: PREPARADOS


@dataclass
class AuthContext:
    """Identidad y tenant de una petición (reutiliza el contexto de la REST API: sale del token)."""
    id_usuario: Optional[str] = None
    id_empresa: Optional[str] = None
    perfil: Optional[str] = None
    scopes: tuple = ()
    auth: str = "anon"      # jwt | apikey | anon


@dataclass
class Tracing:
    """Correlación distribuida (preparada para propagarse entre microservicios)."""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span: Optional[str] = None


@dataclass
class Request:
    """Petición neutral de plataforma (independiente de Flask/HTTP)."""
    operacion: str                       # nombre lógico (p. ej. "communications.list")
    args: dict = field(default_factory=dict)
    auth: AuthContext = field(default_factory=AuthContext)
    tracing: Tracing = field(default_factory=Tracing)
    transporte: str = "rest"


@dataclass
class Error:
    codigo: str
    mensaje: str
    detalle: Any = None


@dataclass
class Response:
    """Respuesta neutral de plataforma."""
    ok: bool
    datos: Any = None
    error: Optional[Error] = None
    trace_id: Optional[str] = None
    ms: float = 0.0

    @classmethod
    def exito(cls, datos, *, trace_id=None, ms=0.0):
        return cls(True, datos=datos, trace_id=trace_id, ms=ms)

    @classmethod
    def fallo(cls, codigo, mensaje, *, detalle=None, trace_id=None):
        return cls(False, error=Error(codigo, mensaje, detalle), trace_id=trace_id)


@dataclass
class Event:
    """Evento de dominio/UI — SIEMPRE viaja por el Corporate Event Bus (nunca un bus paralelo)."""
    tipo: str
    id_empresa: Optional[str] = None
    ref_entidad: Optional[str] = None
    ref_id: Optional[str] = None
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class HealthStatus:
    """Salud publicada por un servicio."""
    estado: str = "unknown"              # ok | degraded | unavailable | unknown
    version: Optional[str] = None
    uptime_s: float = 0.0
    dependencias: dict = field(default_factory=dict)
    latencia_ms: Optional[float] = None
    ultimo_heartbeat: Optional[float] = None

    def as_dict(self):
        return {"estado": self.estado, "version": self.version, "uptime_s": round(self.uptime_s, 1),
                "dependencias": self.dependencias, "latencia_ms": self.latencia_ms,
                "ultimo_heartbeat": self.ultimo_heartbeat}


@dataclass
class ServiceContract:
    """Descriptor de un servicio registrable. `health` es un callable → HealthStatus|dict."""
    nombre: str
    version: str = "1.0.0"
    descripcion: str = ""
    capacidades: tuple = ()               # p. ej. ("comunicaciones", "campañas")
    transportes: tuple = ("rest",)        # cómo se expone/expondría
    dependencias: tuple = ()              # nombres de otros servicios
    rutas: tuple = ()                     # prefijos de ruta (para el Gateway/Routing)
    health: Optional[Callable[[], Any]] = None
    multiempresa: bool = True

    def validar(self):
        errores = []
        if not self.nombre:
            errores.append("nombre requerido")
        for t in self.transportes:
            if t not in TRANSPORTES:
                errores.append(f"transporte no soportado: {t}")
        return (not errores), errores


__all__ = ["TRANSPORTES", "AuthContext", "Tracing", "Request", "Response", "Error", "Event",
           "HealthStatus", "ServiceContract"]
