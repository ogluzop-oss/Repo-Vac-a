"""
Conectores REALES (Bloque 2 — Integraciones reales), listos para activar.

Implementa las llamadas reales a las plataformas externas REUTILIZANDO la infraestructura existente
(OAuth/tokens de `services.correo`, framework `integraciones`, auditoría). Todo está GUARDADO: si falta
el SDK, la credencial o el token, se degrada limpiamente a `no_configurado`/`sdk_ausente` SIN romper —
la funcionalidad se ACTIVA en cuanto la empresa conecta la cuenta correspondiente.

Reglas: **nunca contraseñas** (solo OAuth 2.0). Toda operación se AUDITA. Multiempresa (por cuenta
conectada). No crea motores nuevos: es la capa de ejecución del framework de conectores.

Estado de dependencias en este entorno: Google (`googleapiclient`, `google.oauth2`) DISPONIBLE →
Calendar/Drive/Gmail reales. Microsoft (`msal`) y DocuSign (`docusign_esign`) NO instalados → se usan
llamadas REST con `requests` cuando hay token; si no, degradan. Exchange on-prem (`exchangelib`) → no
soportado sin la lib (degrada).
"""

import logging

logger = logging.getLogger("integraciones.conectores")

_GRAPH = "https://graph.microsoft.com/v1.0"


def _audit(accion, detalle, tabla="integraciones"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("integraciones", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _degradado(conector, motivo="no_configurado", **extra):
    return {"ok": False, "estado": motivo, "conector": conector, **extra}


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE (Calendar · Drive · Gmail) — reutiliza el OAuth cifrado de services.correo
# ══════════════════════════════════════════════════════════════════════════════
def _google_creds(id_correo):
    """Credenciales Google OAuth (refrescadas) reutilizando el buzón conectado. None si no hay."""
    try:
        from src.services.correo.servicio import _credenciales_google
        return _credenciales_google(id_correo)
    except Exception as e:
        logger.debug("google creds: %s", e)
        return None


def _google_service(api, version, id_correo):
    creds = _google_creds(id_correo)
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        return build(api, version, credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.debug("google build %s: %s", api, e)
        return None


def google_calendar(accion, *, id_correo, evento=None, evento_id=None, calendar_id="primary",
                    limite=50):
    """Calendario Google: accion ∈ listar|crear|editar|cancelar. Requiere que la cuenta OAuth tenga el
    scope de Calendar (si no, degrada). Nunca contraseñas."""
    svc = _google_service("calendar", "v3", id_correo)
    if svc is None:
        return _degradado("google_calendar", "no_configurado")
    try:
        if accion == "listar":
            r = svc.events().list(calendarId=calendar_id, maxResults=int(limite),
                                  singleEvents=True, orderBy="startTime").execute()
            _audit("CAL_LISTAR", f"google/{id_correo}")
            return {"ok": True, "estado": "ok", "eventos": r.get("items", [])}
        if accion == "crear":
            ev = svc.events().insert(calendarId=calendar_id, body=evento or {}).execute()
            _audit("CAL_CREAR", f"google/{id_correo}/{ev.get('id')}")
            return {"ok": True, "estado": "ok", "id": ev.get("id")}
        if accion == "editar":
            svc.events().update(calendarId=calendar_id, eventId=evento_id, body=evento or {}).execute()
            _audit("CAL_EDITAR", f"google/{id_correo}/{evento_id}")
            return {"ok": True, "estado": "ok"}
        if accion == "cancelar":
            svc.events().delete(calendarId=calendar_id, eventId=evento_id).execute()
            _audit("CAL_CANCELAR", f"google/{id_correo}/{evento_id}")
            return {"ok": True, "estado": "ok"}
        return _degradado("google_calendar", "accion_desconocida")
    except Exception as e:
        logger.debug("google_calendar %s: %s", accion, e)
        return _degradado("google_calendar", "error", detalle=str(e))


def google_drive_subir(*, id_correo, ruta, nombre=None, mime="application/pdf"):
    """Sube un documento a Google Drive (para adjuntar/archivar). Degrada si falta scope/cuenta."""
    svc = _google_service("drive", "v3", id_correo)
    if svc is None:
        return _degradado("google_drive", "no_configurado")
    try:
        import os

        from googleapiclient.http import MediaFileUpload
        meta = {"name": nombre or os.path.basename(ruta)}
        media = MediaFileUpload(ruta, mimetype=mime, resumable=False)
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        _audit("DRIVE_SUBIR", f"google/{id_correo}/{f.get('id')}")
        return {"ok": True, "estado": "ok", "id": f.get("id"), "link": f.get("webViewLink")}
    except Exception as e:
        logger.debug("google_drive_subir: %s", e)
        return _degradado("google_drive", "error", detalle=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# MICROSOFT GRAPH (Outlook mail · Calendar) — REST con `requests`; token vía config
# ══════════════════════════════════════════════════════════════════════════════
def _msgraph_token(config):
    """Obtiene un token de Graph. Prioriza `config['access_token']`; si hay `msal` + credenciales de
    app (client_credentials), lo adquiere. Devuelve None si no es posible (degrada)."""
    if config and config.get("access_token"):
        return config["access_token"]
    try:
        import msal
    except Exception:
        return None
    try:
        tenant = config.get("tenant_id"); cid = config.get("client_id"); secret = config.get("client_secret")
        if not (tenant and cid and secret):
            return None
        app = msal.ConfidentialClientApplication(
            cid, authority=f"https://login.microsoftonline.com/{tenant}", client_credential=secret)
        r = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        return r.get("access_token")
    except Exception as e:
        logger.debug("msgraph token: %s", e)
        return None


def msgraph(metodo, endpoint, *, config=None, json=None):
    """Llamada REST genérica a Microsoft Graph (Outlook/Exchange Online/Calendar). Degrada sin token."""
    token = _msgraph_token(config or {})
    if not token:
        return _degradado("msgraph", "no_configurado")
    try:
        import requests
        r = requests.request(metodo, _GRAPH + endpoint,
                             headers={"Authorization": f"Bearer {token}",
                                      "Content-Type": "application/json"},
                             json=json, timeout=25)
        _audit("MSGRAPH", f"{metodo} {endpoint} → {r.status_code}")
        try:
            data = r.json()
        except Exception:
            data = None
        return {"ok": r.ok, "estado": "ok" if r.ok else "error", "codigo": r.status_code, "data": data}
    except Exception as e:
        logger.debug("msgraph: %s", e)
        return _degradado("msgraph", "error", detalle=str(e))


def outlook_enviar(*, config, para, asunto, cuerpo, html=False):
    """Envía correo por Outlook/Exchange Online vía Graph (sendMail). Degrada sin token."""
    body = {"message": {"subject": asunto,
                        "body": {"contentType": "HTML" if html else "Text", "content": cuerpo},
                        "toRecipients": [{"emailAddress": {"address": para}}]}}
    return msgraph("POST", "/me/sendMail", config=config, json=body)


def outlook_calendar(accion, *, config, evento=None, evento_id=None):
    """Calendario Outlook/Exchange Online vía Graph: listar|crear|editar|cancelar."""
    if accion == "listar":
        return msgraph("GET", "/me/events", config=config)
    if accion == "crear":
        return msgraph("POST", "/me/events", config=config, json=evento or {})
    if accion == "editar":
        return msgraph("PATCH", f"/me/events/{evento_id}", config=config, json=evento or {})
    if accion == "cancelar":
        return msgraph("DELETE", f"/me/events/{evento_id}", config=config)
    return _degradado("msgraph", "accion_desconocida")


# ══════════════════════════════════════════════════════════════════════════════
# DOCUSIGN (firma electrónica) — REST con `requests`; token OAuth vía config
# ══════════════════════════════════════════════════════════════════════════════
def docusign_enviar_sobre(*, config, sobre):
    """Crea y envía un sobre DocuSign. `config` = {base_uri, account_id, access_token}. Degrada si
    falta configuración/token. Nunca contraseñas."""
    if not (config and config.get("access_token") and config.get("account_id") and config.get("base_uri")):
        return _degradado("docusign", "no_configurado")
    try:
        import requests
        url = f"{config['base_uri']}/restapi/v2.1/accounts/{config['account_id']}/envelopes"
        r = requests.post(url, headers={"Authorization": f"Bearer {config['access_token']}",
                                        "Content-Type": "application/json"}, json=sobre, timeout=30)
        _audit("DOCUSIGN_ENVIAR", f"→ {r.status_code}")
        data = r.json() if r.content else {}
        return {"ok": r.ok, "estado": "ok" if r.ok else "error", "codigo": r.status_code,
                "envelope_id": (data or {}).get("envelopeId"), "data": data}
    except Exception as e:
        logger.debug("docusign_enviar_sobre: %s", e)
        return _degradado("docusign", "error", detalle=str(e))


def docusign_estado(*, config, envelope_id):
    """Consulta el estado/seguimiento de un sobre DocuSign. Degrada sin config."""
    if not (config and config.get("access_token") and config.get("account_id") and config.get("base_uri")):
        return _degradado("docusign", "no_configurado")
    try:
        import requests
        url = (f"{config['base_uri']}/restapi/v2.1/accounts/{config['account_id']}"
               f"/envelopes/{envelope_id}")
        r = requests.get(url, headers={"Authorization": f"Bearer {config['access_token']}"}, timeout=25)
        _audit("DOCUSIGN_ESTADO", f"{envelope_id} → {r.status_code}")
        data = r.json() if r.content else {}
        return {"ok": r.ok, "estado": (data or {}).get("status"), "codigo": r.status_code, "data": data}
    except Exception as e:
        logger.debug("docusign_estado: %s", e)
        return _degradado("docusign", "error", detalle=str(e))
