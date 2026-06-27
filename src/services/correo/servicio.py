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
    """Ruta del client OAuth de Google en disco (fallback heredado).
    1) env GOOGLE_OAUTH_CLIENT_FILE, 2) documentos/google_oauth_client.json."""
    env = os.getenv("GOOGLE_OAUTH_CLIENT_FILE")
    if env and os.path.exists(env):
        return env
    ruta = os.path.join(_dir_documentos(), "google_oauth_client.json")
    return ruta if os.path.exists(ruta) else None


def _resolver_client_oauth() -> dict | None:
    """Resuelve el client OAuth de Google por PRIORIDAD (endurecimiento de seguridad):

      1. Variables de entorno GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET.
      2. Secret Manager (src.services.seguridad.secret_manager) — Vault/KMS futuro.
      3. Fichero env GOOGLE_OAUTH_CLIENT_FILE.
      4. Fichero documentos/google_oauth_client.json (compat. instalaciones antiguas).

    Devuelve {client_id, client_secret, origen} si hay credenciales sin fichero, o
    {ruta_fichero, origen} si solo hay JSON en disco, o None si no hay configuración.
    NO se rompe ninguna instalación existente: el fichero sigue siendo fallback válido."""
    # 1) Variables de entorno directas.
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    csec = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    if cid and csec:
        return {"client_id": cid, "client_secret": csec, "origen": "env"}
    # 2) Secret Manager (abstracción Vault/KMS; degrada a entorno en su capa).
    try:
        from src.services.seguridad import secret_manager
        cid = secret_manager.obtener_secreto("GOOGLE_OAUTH_CLIENT_ID")
        csec = secret_manager.obtener_secreto("GOOGLE_OAUTH_CLIENT_SECRET")
        if cid and csec:
            return {"client_id": cid, "client_secret": csec, "origen": "secret_manager"}
    except Exception as e:
        logger.debug("secret_manager no disponible: %s", e)
    # 3 y 4) Fichero JSON en disco (fallback heredado).
    ruta = _client_secret_path()
    if ruta:
        return {"ruta_fichero": ruta, "origen": "file"}
    return None


def oauth_google_configurado() -> bool:
    """True si hay client OAuth de Google (env/secret manager/fichero) y la librería disponible."""
    if _resolver_client_oauth() is None:
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
    conf = _resolver_client_oauth()
    if not conf:
        return False, ("Falta el client OAuth de Google. Define GOOGLE_OAUTH_CLIENT_ID/"
                       "GOOGLE_OAUTH_CLIENT_SECRET (recomendado), configúralo en el secret "
                       "manager, o coloca 'google_oauth_client.json' en documentos/.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        if conf.get("client_id"):
            # Sin fichero en disco: construye la config del cliente en memoria.
            client_config = {"installed": {
                "client_id": conf["client_id"],
                "client_secret": conf["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost"],
            }}
            flujo = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        else:
            flujo = InstalledAppFlow.from_client_secrets_file(conf["ruta_fichero"], GMAIL_SCOPES)
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
    # Resuelve client_id/secret por prioridad (env → secret manager → fichero).
    conf = _resolver_client_oauth() or {}
    cid, csec = conf.get("client_id"), conf.get("client_secret")
    if not (cid and csec) and conf.get("ruta_fichero"):
        try:
            import json
            data = json.load(open(conf["ruta_fichero"], encoding="utf-8"))
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
    elif proveedor == "smtp":
        ok, msg = _enviar_smtp(c, destinatario, asunto, cuerpo, adjuntos)
    else:
        ok, msg = _enviar_simulado(c, destinatario, asunto, cuerpo, adjuntos)

    if ok:
        correo_db.marcar_sincronizacion(id_correo)
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("sistema", "CORREO_ENVIADO", "correos_corporativos",
                          f"de {remite} a {destinatario}: {asunto}")
        except Exception:
            pass
    return ok, msg


def _enviar_smtp(c: dict, destinatario, asunto, cuerpo, adjuntos) -> tuple[bool, str]:
    """Envío por SMTP genérico (host/puerto/credenciales del buzón). Requiere config SMTP."""
    try:
        import smtplib
        host = c.get("smtp_host"); port = int(c.get("smtp_port") or 587)
        if not host:
            return False, "SMTP no configurado en el buzón."
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos)
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            if c.get("smtp_usuario"):
                s.login(c["smtp_usuario"], c.get("smtp_password") or "")
            s.sendmail(c["direccion"], [destinatario], mime.as_string())
        return True, f"Enviado por SMTP a {destinatario}."
    except Exception as e:
        logger.error("Error enviando por SMTP: %s", e)
        return False, f"Error al enviar por SMTP: {e}"


def sincronizar_imap(id_correo: str, *, limite=20) -> int:
    """Descarga correos por IMAP y los persiste (correos_recibidos). Requiere config IMAP.
    Devuelve el nº de mensajes nuevos guardados. Best-effort (red); no usado en tests."""
    c = correo_db.obtener_correo(id_correo)
    if not c or not c.get("imap_host"):
        return 0
    try:
        import imaplib
        import email as _email
        n = 0
        srv = imaplib.IMAP4_SSL(c["imap_host"], int(c.get("imap_port") or 993))
        srv.login(c.get("imap_usuario") or c["direccion"], c.get("imap_password") or "")
        srv.select("INBOX")
        _typ, datos = srv.search(None, "ALL")
        ids = (datos[0].split() or [])[-int(limite):]
        for i in ids:
            _t, msg_data = srv.fetch(i, "(RFC822)")
            msg = _email.message_from_bytes(msg_data[0][1])
            cuerpo = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        cuerpo = part.get_payload(decode=True).decode("utf-8", "ignore"); break
            else:
                cuerpo = (msg.get_payload(decode=True) or b"").decode("utf-8", "ignore")
            if correo_db.guardar_recibido(id_correo, msg.get("From"), msg.get("Subject"),
                                          cuerpo, message_id=msg.get("Message-ID"), fecha=None):
                n += 1
        srv.logout()
        correo_db.marcar_sincronizacion(id_correo)
        return n
    except Exception as e:
        logger.error("sincronizar_imap: %s", e)
        return 0


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
