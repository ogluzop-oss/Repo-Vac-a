"""
Cliente YouTube — YouTube Data API v3 real: comentarios (listar/responder, equivalente de
"mensajería" en una plataforma sin DMs públicas) y métricas básicas por vídeo. La publicación de
vídeo real requiere una subida resumable multi-petición (`videos.insert` con el binario) — fuera
del alcance REST simple de este cliente; se deja degradada honestamente en vez de simularla.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.transporte import get_transporte

logger = logging.getLogger("redes_sociales.plataformas.youtube")

BASE_URL = os.getenv("YOUTUBE_DATA_API_HOST", "https://www.googleapis.com/youtube/v3")


def _degradado(motivo="no_configurado", **extra):
    return {"ok": False, "estado": motivo, "plataforma": "youtube", **extra}


def _token(id_cuenta, id_empresa=None):
    return _cuentas.obtener_token(id_cuenta, id_empresa=id_empresa)


def listar_mensajes(*_a, **_k) -> dict:
    return _degradado("no_disponible_en_la_plataforma",
                      detalle="YouTube no tiene mensajería directa; usa comentarios como canal de interacción.")


def listar_comentarios(id_cuenta, id_externo_video, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "GET", f"{BASE_URL}/commentThreads", token=token,
            params={"part": "snippet", "videoId": id_externo_video, "maxResults": 50},
            plataforma="youtube")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "comentarios": data.get("items", [])}


def responder_comentario(id_cuenta, id_externo_comentario_padre, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "POST", f"{BASE_URL}/comments", token=token, params={"part": "snippet"},
            json={"snippet": {"parentId": id_externo_comentario_padre, "textOriginal": texto}},
            plataforma="youtube")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "id_externo": data.get("id")}


def publicar(*_a, **_k) -> dict:
    return _degradado("no_implementado",
                      detalle="La subida de vídeo a YouTube requiere subida resumable binaria; "
                              "fuera de alcance de este cliente REST simple.")


def obtener_metricas(id_cuenta, id_externo_video, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "GET", f"{BASE_URL}/videos", token=token,
            params={"part": "statistics", "id": id_externo_video}, plataforma="youtube")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    items = data.get("items", [])
    return {"ok": True, "metricas": items[0].get("statistics", {}) if items else {}}
