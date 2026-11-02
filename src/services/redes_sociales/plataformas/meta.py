"""
Cliente Meta Graph API — Instagram (DMs/comentarios/publicación vía IG Business) y Facebook
(Messenger/comentarios/publicación de página). Llamadas REALES a
`https://graph.facebook.com/<versión>` cuando hay token conectado; degrada honestamente si no.

Nota de alcance (auditoría): el ÚNICO punto previo del repo que tocaba Graph API era
`services.ccp.canales.omnichannel.WhatsAppChannel` (WhatsApp Business, saliente) — dominio
distinto (no mensajería de IG/FB), así que esto es cliente nuevo, no una duplicidad.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import IntegracionError
from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.transporte import get_transporte

logger = logging.getLogger("redes_sociales.plataformas.meta")

API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


def _degradado(motivo="no_configurado", **extra):
    return {"ok": False, "estado": motivo, "plataforma": "meta", **extra}


def _token(id_cuenta, id_empresa=None):
    return _cuentas.obtener_token(id_cuenta, id_empresa=id_empresa)


def _llamar(metodo, path, token, *, params=None, json=None):
    try:
        data = get_transporte().request(metodo, f"{BASE_URL}/{path.lstrip('/')}", token=None,
                                        params={**(params or {}), "access_token": token},
                                        json=json, plataforma="meta")
        return {"ok": True, "data": data}
    except IntegracionError as e:
        return _degradado("error", detalle=e.to_dict())


def listar_conversaciones(id_cuenta, id_externo_pagina, *, plataforma_canal="instagram",
                          id_empresa=None) -> dict:
    """`plataforma_canal`: 'instagram' o 'messenger' (parámetro real de Graph `platform=`)."""
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    r = _llamar("GET", f"{id_externo_pagina}/conversations", token,
               params={"platform": plataforma_canal,
                       "fields": "participants,updated_time,snippet"})
    if not r["ok"]:
        return r
    return {"ok": True, "conversaciones": r["data"].get("data", [])}


def listar_mensajes(id_cuenta, id_externo_conversacion, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    r = _llamar("GET", f"{id_externo_conversacion}/messages", token,
               params={"fields": "message,from,to,created_time,attachments"})
    if not r["ok"]:
        return r
    return {"ok": True, "mensajes": r["data"].get("data", [])}


def enviar_mensaje(id_cuenta, id_externo_pagina, destinatario_externo_id, texto, *,
                   id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    r = _llamar("POST", f"{id_externo_pagina}/messages", token,
               json={"recipient": {"id": destinatario_externo_id}, "message": {"text": texto}})
    if not r["ok"]:
        return r
    return {"ok": True, "id_externo": r["data"].get("message_id")}


def listar_comentarios(id_cuenta, id_externo_publicacion, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    r = _llamar("GET", f"{id_externo_publicacion}/comments", token,
               params={"fields": "message,from,created_time,like_count"})
    if not r["ok"]:
        return r
    return {"ok": True, "comentarios": r["data"].get("data", [])}


def responder_comentario(id_cuenta, id_externo_comentario, texto, *, id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    r = _llamar("POST", f"{id_externo_comentario}/comments", token, json={"message": texto})
    if not r["ok"]:
        return r
    return {"ok": True, "id_externo": r["data"].get("id")}


def publicar(id_cuenta, id_externo_pagina, *, texto=None, url_imagen=None, canal="facebook",
             id_empresa=None) -> dict:
    """`canal`: 'facebook' (feed de página) o 'instagram' (IG Business: media + media_publish)."""
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    if canal == "instagram":
        if not url_imagen:
            return _degradado("instagram_requiere_imagen_publica")
        r1 = _llamar("POST", f"{id_externo_pagina}/media", token,
                    json={"image_url": url_imagen, "caption": texto or ""})
        if not r1["ok"]:
            return r1
        id_creacion = r1["data"].get("id")
        r2 = _llamar("POST", f"{id_externo_pagina}/media_publish", token,
                    json={"creation_id": id_creacion})
        if not r2["ok"]:
            return r2
        return {"ok": True, "id_externo": r2["data"].get("id")}
    r = _llamar("POST", f"{id_externo_pagina}/feed", token, json={"message": texto or ""})
    if not r["ok"]:
        return r
    return {"ok": True, "id_externo": r["data"].get("id")}


def obtener_metricas(id_cuenta, id_externo_publicacion, *, canal="facebook", id_empresa=None) -> dict:
    token = _token(id_cuenta, id_empresa)
    if not token:
        return _degradado()
    metricas = ("impressions,reach,engagement" if canal == "instagram"
               else "post_impressions,post_engaged_users,post_clicks")
    r = _llamar("GET", f"{id_externo_publicacion}/insights", token, params={"metric": metricas})
    if not r["ok"]:
        return r
    return {"ok": True, "metricas": r["data"].get("data", [])}
