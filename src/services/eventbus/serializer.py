"""Serializer del Event Bus (Fase III · B1) — JSON estable de payloads de evento."""

import datetime
import json


def _default(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    return str(o)


def serializar(payload) -> str:
    try:
        return json.dumps(payload or {}, default=_default, ensure_ascii=False)
    except Exception:
        return "{}"


def deserializar(texto):
    if not texto:
        return {}
    if isinstance(texto, dict):
        return texto
    try:
        return json.loads(texto)
    except Exception:
        return {}
