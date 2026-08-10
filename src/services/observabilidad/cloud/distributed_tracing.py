"""
Cloud Observability · Distributed Tracing (Fase VI · Bloque 12). EXTIENDE el OpenTelemetry existente
(`observabilidad.tracing`) y el Correlation ID (`observabilidad.correlation`) hacia trazas distribuidas.
Un `TraceContext` global une: Trace ID · Span ID · Correlation ID · Communication ID · Workflow ID,
para seguir una operación a través de nodos/servicios. No modifica los módulos existentes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


def _nuevo_id(prefijo):
    try:
        from src.services.observabilidad import correlation
        return correlation.nuevo(prefijo)
    except Exception:
        return f"{prefijo}-{uuid.uuid4().hex[:16]}"


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: _nuevo_id("trace"))
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span: str = None
    correlation_id: str = field(default_factory=lambda: _nuevo_id("corr"))
    communication_id: str = None      # CCP Communication ID (si aplica)
    workflow_id: str = None           # Workflow ID (si aplica)

    def hijo(self) -> "TraceContext":
        """Nuevo span dentro de la MISMA traza (propaga trace/correlation/communication/workflow)."""
        return TraceContext(trace_id=self.trace_id, span_id=uuid.uuid4().hex[:16],
                            parent_span=self.span_id, correlation_id=self.correlation_id,
                            communication_id=self.communication_id, workflow_id=self.workflow_id)

    def headers(self) -> dict:
        """Cabeceras de propagación entre nodos/servicios (W3C-like + IDs corporativos)."""
        h = {"X-Trace-Id": self.trace_id, "X-Span-Id": self.span_id,
             "X-Correlation-Id": self.correlation_id}
        if self.parent_span:
            h["X-Parent-Span"] = self.parent_span
        if self.communication_id:
            h["X-Communication-Id"] = self.communication_id
        if self.workflow_id:
            h["X-Workflow-Id"] = self.workflow_id
        return h

    def as_dict(self):
        return {"trace_id": self.trace_id, "span_id": self.span_id, "parent_span": self.parent_span,
                "correlation_id": self.correlation_id, "communication_id": self.communication_id,
                "workflow_id": self.workflow_id}


def nuevo_trace(*, communication_id=None, workflow_id=None) -> TraceContext:
    return TraceContext(communication_id=communication_id, workflow_id=workflow_id)


def desde_headers(headers) -> TraceContext:
    """Reconstruye el contexto a partir de las cabeceras recibidas de otro nodo/servicio."""
    h = headers or {}
    return TraceContext(trace_id=h.get("X-Trace-Id") or _nuevo_id("trace"),
                        span_id=uuid.uuid4().hex[:16], parent_span=h.get("X-Span-Id"),
                        correlation_id=h.get("X-Correlation-Id") or _nuevo_id("corr"),
                        communication_id=h.get("X-Communication-Id"),
                        workflow_id=h.get("X-Workflow-Id"))


def span(nombre, ctx=None):
    """Abre un span reutilizando el tracing OTel existente (degradable)."""
    try:
        from src.services.observabilidad import tracing
        return tracing.span(nombre, **(ctx.as_dict() if ctx else {}))
    except Exception:
        from contextlib import nullcontext
        return nullcontext()


__all__ = ["TraceContext", "nuevo_trace", "desde_headers", "span"]
