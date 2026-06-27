"""
Correlation ID transversal (OBS-2).

Identificador único por operación (request API, ejecución de workflow, job del scheduler,
webhook) que se propaga vía contextvar y se inyecta en los logs. Permite reconstruir una
operación extremo a extremo. Degrada sin romper si no se usa.
"""

import contextvars
import logging
import uuid

_CID = contextvars.ContextVar("correlation_id", default=None)


def nuevo(prefijo="op") -> str:
    cid = f"{prefijo}-{uuid.uuid4().hex[:16]}"
    _CID.set(cid)
    return cid


def set_id(cid):
    _CID.set(cid)


def get_id():
    return _CID.get()


class _Ctx:
    def __init__(self, cid=None, prefijo="op"):
        self._cid = cid or f"{prefijo}-{uuid.uuid4().hex[:16]}"
        self._token = None

    def __enter__(self):
        self._token = _CID.set(self._cid)
        return self._cid

    def __exit__(self, *a):
        try:
            _CID.reset(self._token)
        except Exception:
            _CID.set(None)


def contexto(cid=None, prefijo="op"):
    """Context manager que fija el correlation_id durante el bloque."""
    return _Ctx(cid, prefijo)


class CorrelationFilter(logging.Filter):
    """Filtro de logging que añade `correlation_id` a cada registro."""
    def filter(self, record):
        record.correlation_id = _CID.get() or "-"
        return True
