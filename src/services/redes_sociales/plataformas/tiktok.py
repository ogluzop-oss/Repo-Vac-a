"""
Cliente TikTok — publicación real vía Content Posting API + métricas vía la misma API, y
COMENTARIOS reales vía la TikTok Business API (Community Management: `business-api.tiktok.com`,
permiso `biz.comment.manage`), DISTINTA de la API de consumo (`open.tiktokapis.com`) usada para
publicar/medir. Corrección de un error de alcance de una fase anterior: se dijo que TikTok no
exponía comentarios a apps de terceros — es cierto para la API de consumo pública, pero NO para
una cuenta TikTok Business conectada con el permiso de gestión de comunidad, que es exactamente el
tipo de cuenta que una empresa usa para su presencia corporativa (petición explícita: los
comentarios de TikTok deben aparecer SÍ O SÍ en la bandeja). Mensajería directa (DM) SÍ sigue sin
tener API pública para terceros en ningún nivel — eso no ha cambiado, degrada honestamente.

Esto es DISTINTO del conector `tiktok_shop` ya existente (catálogo/pedidos de tienda).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.transporte import get_transporte

logger = logging.getLogger("redes_sociales.plataformas.tiktok")

BASE_URL = os.getenv("TIKTOK_OPEN_API_HOST", "https://open.tiktokapis.com/v2")
BUSINESS_API_URL = os.getenv("TIKTOK_BUSINESS_API_HOST",
                             "https://business-api.tiktok.com/open_api/v1.3")


def _degradado(motivo="no_configurado", **extra):
    return {"ok": False, "estado": motivo, "plataforma": "tiktok", **extra}


def _token(id_cuenta, id_empresa=None):
    return _cuentas.obtener_token(id_cuenta, id_empresa=id_empresa)


def _llamar_business(metodo, path, token, *, params=None, json=None):
    """La Business API de TikTok autentica con la cabecera `Access-Token` (NO `Authorization:
    Bearer`) — se pasa como `headers` explícito y `token=None` para que el transporte genérico no
    añada también un `Authorization` que esta API no espera."""
    try:
        data = get_transporte().request(
            metodo, f"{BUSINESS_API_URL}/{path.lstrip('/')}", token=None,
            headers={"Access-Token": token or ""}, params=params, json=json, plataforma="tiktok")
    except IntegracionError as e:
        return {"ok": False, "estado": "error", "detalle": e.to_dict()}
    codigo = data.get("code")
    if codigo not in (0, None):
        return {"ok": False, "estado": "error_api_business",
               "detalle": data.get("message") or data}
    return {"ok": True, "data": (data.get("data") or {})}


def listar_mensajes(id_cuenta, *_a, id_empresa=None, **_k) -> dict:
    return _degradado("no_disponible_en_la_plataforma",
                      detalle="TikTok no ofrece una API pública de mensajería directa (DM) para "
                              "apps de terceros, ni siquiera a nivel de cuenta Business.")


def listar_comentarios(id_cuenta, id_externo_video, *, id_empresa=None) -> dict:
    """Vía TikTok Business API (comentarios reales de un vídeo propio, requiere cuenta Business
    conectada con permiso de gestión de comunidad)."""
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == id_cuenta), None)
    if not cuenta:
        return _degradado("cuenta_no_encontrada")
    r = _llamar_business("GET", "/comment/list/", token,
                         params={"business_id": cuenta["id_externo"], "video_id": id_externo_video})
    if not r["ok"]:
        return r
    return {"ok": True, "comentarios": r["data"].get("comments", [])}


def responder_comentario(id_cuenta, id_externo_comentario, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == id_cuenta), None)
    if not cuenta:
        return _degradado("cuenta_no_encontrada")
    r = _llamar_business("POST", "/comment/reply/", token,
                         json={"business_id": cuenta["id_externo"],
                               "comment_id": id_externo_comentario, "text": texto})
    if not r["ok"]:
        return r
    return {"ok": True, "id_externo": r["data"].get("comment_id")}


def publicar(id_cuenta, *, ruta_video_url, titulo=None, id_empresa=None) -> dict:
    """Content Posting API: inicia la publicación de un vídeo ya alojado en una URL accesible."""
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "POST", f"{BASE_URL}/post/publish/video/init/", token=token,
            json={"post_info": {"title": titulo or ""},
                  "source_info": {"source": "PULL_FROM_URL", "video_url": ruta_video_url}},
            plataforma="tiktok")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    return {"ok": True, "id_externo": (data.get("data") or {}).get("publish_id")}


def obtener_metricas(id_cuenta, id_externo_publicacion, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    try:
        data = get_transporte().request(
            "POST", f"{BASE_URL}/video/query/", token=token,
            json={"filters": {"video_ids": [id_externo_publicacion]}},
            params={"fields": "id,view_count,like_count,comment_count,share_count"},
            plataforma="tiktok")
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())
    videos = (data.get("data") or {}).get("videos", [])
    return {"ok": True, "metricas": videos[0] if videos else {}}
