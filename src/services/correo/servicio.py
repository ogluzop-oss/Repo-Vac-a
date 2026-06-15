"""
Servicio de envío del correo corporativo.

Despacha por proveedor del buzón:
  * 'simulado'  → NO envía de verdad: guarda el correo como .eml en disco
    (documentos/correo_enviados/<EMP>/...) y marca sincronización. Permite que
    todo el flujo (UI, hook de documentos) funcione SIN credenciales ni red.
  * 'google'    → envío real con la API de Gmail usando los tokens OAuth cifrados.
  * 'smtp'      → reservado (no implementado todavía; degrada a simulado).

OAuth 2.0 (Google): los tokens se guardan CIFRADOS (ver src/db/correo + cripto).
NUNCA se guardan contraseñas. El flujo requiere un client OAuth de Google
(documentos/google_oauth_client.json o env GOOGLE_OAUTH_CLIENT_FILE); si no está,
`oauth_google_configurado()` devuelve False y la UI lo indica.
"""

import base64
import logging
import os
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from src.db import correo as correo_db
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("correo.servicio")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _dir_documentos() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "documentos",
    )
    return base


def _client_secret_path() -> str | None:
    """Ruta del client OAuth de Google (JSON descargado de Google Cloud)."""
    env = os.getenv("GOOGLE_OAUTH_CLIENT_FILE")
    if env and os.path.exists(env):
        return env
    ruta = os.path.join(_dir_documentos(), "google_oauth_client.json")
    return ruta if os.path.exists(ruta) else None


def oauth_google_configurado() -> bool:
    """True si existe el client OAuth de Google y la librería está disponible."""
    if _client_secret_path() is None:
        return False
    try:
        import google_auth_oauthlib.flow  # noqa: F401
        return True
    except Exception:
        return False


def estado_oauth(id_correo: str) -> dict:
    """Estado de conexión OAuth de un buzón: {conectado, proveedor, configurable}."""
    tok = correo_db.obtener_tokens(id_correo)
    return {
        "conectado": bool(tok and (tok.get("refresh_token") or tok.get("access_token"))),
        "proveedor": (tok or {}).get("proveedor"),
        "google_configurable": oauth_google_configurado(),
    }


# ============================================================
# OAUTH GOOGLE (flujo de escritorio — abre el navegador para consentir)
# ============================================================
def iniciar_oauth_google(id_correo: str) -> tuple[bool, str]:
    """Lanza el flujo OAuth 2.0 de Google para un buzón y guarda los tokens
    CIFRADOS. Requiere el client OAuth (google_oauth_client.json). Abre el
    navegador del usuario para el consentimiento (InstalledAppFlow)."""
    ruta = _client_secret_path()
    if not ruta:
        return False, ("Falta el client OAuth de Google. Coloca 'google_oauth_client.json' "
                       "en la carpeta documentos/ (descárgalo de Google Cloud Console).")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flujo = InstalledAppFlow.from_client_secrets_file(ruta, GMAIL_SCOPES)
        cred = flujo.run_local_server(port=0)
        expira = cred.expiry.strftime("%Y-%m-%d %H:%M:%S") if getattr(cred, "expiry", None) else None
        correo_db.guardar_tokens(
            id_correo, "google",
            access_token=cred.token,
            refresh_token=cred.refresh_token,
            scope=" ".join(GMAIL_SCOPES),
            expira_en=expira,
        )
        correo_db.actualizar_correo(id_correo, proveedor="google", estado="activo")
        correo_db.marcar_sincronizacion(id_correo)
        return True, "Cuenta de Google conectada correctamente."
    except Exception as e:
        logger.error("Error OAuth Google: %s", e)
        return False, f"No se pudo conectar con Google: {e}"


def _credenciales_google(id_correo: str):
    """Reconstruye google Credentials desde los tokens cifrados, refrescando si
    hace falta (y actualizando el access token guardado)."""
    tok = correo_db.obtener_tokens(id_correo)
    if not tok:
        return None
    ruta = _client_secret_path()
    cid = csec = None
    if ruta:
        try:
            import json
            data = json.load(open(ruta, encoding="utf-8"))
            blob = data.get("installed") or data.get("web") or {}
            cid, csec = blob.get("client_id"), blob.get("client_secret")
        except Exception:
            pass
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        cred = Credentials(
            token=tok.get("access_token"),
            refresh_token=tok.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cid, client_secret=csec,
            scopes=(tok.get("scope") or "").split() or GMAIL_SCOPES,
        )
        if cred.refresh_token and (not cred.valid):
            cred.refresh(Request())
            exp = cred.expiry.strftime("%Y-%m-%d %H:%M:%S") if getattr(cred, "expiry", None) else None
            correo_db.guardar_tokens(id_correo, "google", access_token=cred.token,
                                     refresh_token=cred.refresh_token,
                                     scope=tok.get("scope"), expira_en=exp)
        return cred
    except Exception as e:
        logger.error("Error credenciales Google: %s", e)
        return None


# ============================================================
# CONSTRUCCIÓN DEL MENSAJE
# ============================================================
def _construir_mime(remite: str, destinatario: str, asunto: str, cuerpo: str, adjuntos):
    msg = MIMEMultipart()
    msg["From"] = remite
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo or "", "plain", "utf-8"))
    for ruta in (adjuntos or []):
        try:
            with open(ruta, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{os.path.basename(ruta)}"')
            msg.attach(part)
        except Exception as e:
            logger.warning("No se pudo adjuntar %s: %s", ruta, e)
    return msg


# ============================================================
# ENVÍO (despacho por proveedor)
# ============================================================
def enviar_documento(id_correo: str, destinatario: str, asunto: str,
                     cuerpo: str = "", adjuntos=None) -> tuple[bool, str]:
    """Envía un documento desde el buzón corporativo indicado. Devuelve (ok, msg)."""
    c = correo_db.obtener_correo(id_correo)
    if not c:
        return False, "Buzón no encontrado."
    if c.get("estado") != "activo":
        return False, "El buzón no está activo."
    remite = c["direccion"]
    proveedor = c.get("proveedor", "simulado")
    adjuntos = adjuntos or []

    if proveedor == "google":
        ok, msg = _enviar_google(c, destinatario, asunto, cuerpo, adjuntos)
    else:
        ok, msg = _enviar_simulado(c, destinatario, asunto, cuerpo, adjuntos)

    if ok:
        correo_db.marcar_sincronizacion(id_correo)
    return ok, msg


def _enviar_google(c: dict, destinatario, asunto, cuerpo, adjuntos) -> tuple[bool, str]:
    cred = _credenciales_google(c["id_correo"])
    if cred is None:
        return False, "La cuenta de Google no está conectada (OAuth). Conéctala primero."
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=cred, cache_discovery=False)
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True, f"Enviado a {destinatario} desde {c['direccion']}."
    except Exception as e:
        logger.error("Error enviando por Gmail: %s", e)
        return False, f"Error al enviar por Gmail: {e}"


def _enviar_simulado(c: dict, destinatario, asunto, cuerpo, adjuntos) -> tuple[bool, str]:
    """No envía de verdad: guarda el .eml en disco para demostrar el flujo."""
    try:
        carpeta = os.path.join(_dir_documentos(), "correo_enviados",
                               empresa_actual_id())
        os.makedirs(carpeta, exist_ok=True)
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos)
        # Marca de tiempo con microsegundos + sufijo aleatorio para que dos correos
        # al mismo destinatario en el mismo segundo no compartan nombre (ni se pisen).
        nombre = datetime.now().strftime("%Y%m%d_%H%M%S_%f_") + \
            "".join(ch for ch in destinatario if ch.isalnum())[:20] + \
            "_" + os.urandom(3).hex() + ".eml"
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, "wb") as f:
            f.write(mime.as_bytes())
        logger.info("[SIMULADO] Correo guardado: %s", ruta)
        return True, (f"(Modo simulado) Correo preparado desde {c['direccion']} "
                      f"para {destinatario}. Guardado en documentos/correo_enviados/.")
    except Exception as e:
        logger.error("Error en envío simulado: %s", e)
        return False, f"Error en envío simulado: {e}"
