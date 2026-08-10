"""
Cloud Observability · Log Collector (Fase VI · Bloque 12). Recolector CENTRALIZADO de logs preparado
para backends distribuidos: ELK, OpenSearch y Loki. NO envía a un backend real (sin credenciales/red):
define el contrato y un backend en memoria/local para pruebas. Reutiliza el logging JSON existente.
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger("cloud.logs")

BACKENDS = ("local", "elk", "opensearch", "loki")

_BUFFER = []          # backend local (en memoria) para pruebas
_CONFIG = {"backend": "local", "max_buffer": 5000}


def configurar(backend="local", **opts):
    if backend in BACKENDS:
        _CONFIG["backend"] = backend
    _CONFIG.update({k: v for k, v in opts.items() if k != "backend"})
    return dict(_CONFIG)


def recolectar(nivel, mensaje, *, servicio=None, nodo=None, region=None, trace_id=None, extra=None):
    """Recolecta un evento de log estructurado. En 'local' lo bufferiza; en elk/opensearch/loki
    (PREPARADO) se enviaría al backend distribuido con el mismo documento JSON."""
    doc = {"ts": time.time(), "nivel": nivel, "mensaje": mensaje, "servicio": servicio,
           "nodo": nodo, "region": region, "trace_id": trace_id, **(extra or {})}
    if _CONFIG["backend"] == "local":
        _BUFFER.append(doc)
        if len(_BUFFER) > _CONFIG["max_buffer"]:
            del _BUFFER[0:len(_BUFFER) - _CONFIG["max_buffer"]]
    else:
        # Preparado: aquí iría el envío HTTP/bulk al backend (ELK/OpenSearch/Loki).
        logger.debug("log→%s: %s", _CONFIG["backend"], json.dumps(doc))
    return doc


def consultar(*, nivel=None, servicio=None, limite=100) -> list:
    datos = _BUFFER
    if nivel:
        datos = [d for d in datos if d.get("nivel") == nivel]
    if servicio:
        datos = [d for d in datos if d.get("servicio") == servicio]
    return list(reversed(datos))[:limite]


def limpiar():
    _BUFFER.clear()


def descriptor() -> dict:
    return {"backend": _CONFIG["backend"], "backends_soportados": list(BACKENDS),
            "eventos_bufferizados": len(_BUFFER)}


__all__ = ["BACKENDS", "configurar", "recolectar", "consultar", "limpiar", "descriptor"]
