"""
Cliente X (Twitter) — X API v2 real: DMs (`dm_conversations`), menciones y publicación de
tweets/respuestas. Nombrado `x.py` (no `twitter.py`) para seguir el nombre actual de la
plataforma.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.transporte import get_transporte

logger = logging.getLogger("redes_sociales.plataformas.x")

BASE_URL = os.getenv("X_API_HOST", "https://api.x.com/2")


def _degradado(motivo="no_configurado", **extra):
    return {"ok": False, "estado": motivo, "plataforma": "x", **extra}


def _token(id_cuenta, id_empresa=None):
    return _cuentas.obtener_token(id_cuenta, id_empresa=id_empresa)


def listar_mensajes(id_cuenta, id_externo_conversacion, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "GET", f"{BASE_URL}/dm_conversations/{id_externo_conversacion}/dm_events",
            token=token, plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "mensajes": data.get("data", [])}


def enviar_mensaje(id_cuenta, destinatario_externo_id, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "POST", f"{BASE_URL}/dm_conversations/with/{destinatario_externo_id}/messages",
            token=token, json={"text": texto}, plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "id_externo": data.get("dm_conversation_id")}


def listar_menciones(id_cuenta, id_externo_usuario, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "GET", f"{BASE_URL}/users/{id_externo_usuario}/mentions", token=token,
            params={"tweet.fields": "author_id,created_at,text"}, plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "menciones": data.get("data", [])}


def responder_comentario(id_cuenta, id_externo_tweet_padre, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "POST", f"{BASE_URL}/tweets", token=token,
            json={"text": texto, "reply": {"in_reply_to_tweet_id": id_externo_tweet_padre}},
            plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "id_externo": (data.get("data") or {}).get("id")}


def publicar(id_cuenta, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request("POST", f"{BASE_URL}/tweets", token=token,
                                        json={"text": texto}, plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "id_externo": (data.get("data") or {}).get("id")}


def obtener_metricas(id_cuenta, id_externo_tweet, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "GET", f"{BASE_URL}/tweets/{id_externo_tweet}", token=token,
            params={"tweet.fields": "public_metrics"}, plataforma="x")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "metricas": (data.get("data") or {}).get("public_metrics", {})}
