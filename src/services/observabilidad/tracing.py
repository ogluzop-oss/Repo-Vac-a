"""
Tracing distribuido (OBS-7) — OpenTelemetry si está instalado; si no, no-op (degrada).
"""

import logging
logger = logging.getLogger("obs.tracing")

try:
    from opentelemetry import trace as _otel_trace
    _TRACER = _otel_trace.get_tracer("smart_manager")
    _OTEL = True
except Exception:
    _OTEL = False


class _NoSpan:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def set_attribute(self, *a, **k): pass


def span(nombre, **attrs):
    """Context manager de span (OTel real o no-op)."""
    if _OTEL:
        s = _TRACER.start_as_current_span(nombre)
        return s
    return _NoSpan()


def disponible() -> bool:
    return _OTEL
