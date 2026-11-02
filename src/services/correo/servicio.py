"""
Servicio de envío del correo corporativo.

Despacha por proveedor del buzón:
  * 'simulado'  → NO envía de verdad: guarda el correo como .eml en disco
    (documentos/correo_enviados/<EMP>/...) y marca sincronización. Permite que
    todo el flujo (UI, hook de documentos) funcione SIN credenciales ni red.
  * 'google'    → envío real con la API de Gmail usando los tokens OAuth cifrados.
  * 'smtp'      → envío real por SMTP+STARTTLS (`_enviar_smtp`), usando host/puerto/usuario/
    contraseña de `db.correo.guardar_smtp` (contraseña cifrada en reposo) — alternativa sin OAuth
    ni Google Cloud Console (p. ej. Gmail con una contraseña de aplicación).

OAuth 2.0 (Google): los tokens se guardan CIFRADOS (ver src/db/correo + cripto).
NUNCA se guardan contraseñas. La app ships un client OAuth de Google CENTRALIZADO
(`assets/google_oauth_client.json`, un único proyecto de Google Cloud de Smart
Manager): el cliente no es responsabilidad del operador/instalación — nunca se le
pide crear su propio proyecto de Google Cloud ni descargar un client-secret. Env
vars / secret manager siguen disponibles como override explícito (p. ej. despliegues
white-label con marca propia); los ficheros en documentos/ siguen como fallback
heredado de instalaciones antiguas (Strangler Pattern — ver `_resolver_client_oauth`
para el orden exacto). Si NADA de eso está presente en un despliegue dado,
`oauth_google_configurado()` devuelve False y la UI lo indica con un mensaje honesto
(nunca le dice al cliente que descargue nada de Google Cloud Console).
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

# Scopes OAuth de Google: envío (histórico) + lectura de Gmail/Calendar (añadidos para la
# bandeja real de Correo y la sincronización de Planificar Citas). SOLO lectura (.readonly) por
# mínimo privilegio: esta integración es de solo LECTURA (Google → Smart Manager), nunca escribe
# en el Calendar/Gmail real del cliente (ver conectores.py para esas acciones, no usadas aún).
#
# IMPORTANTE (reconsentimiento): las cuentas YA conectadas antes de este cambio tienen un token
# guardado con el scope antiguo (solo gmail.send) — seguirán pudiendo ENVIAR, pero cualquier
# llamada de lectura (sincronizar_gmail_api / calendario.sincronizar_google) fallará con un 403
# de Google hasta que el usuario pulse "CONECTAR (OAuth)" de nuevo en _BuzonesDialog para
# reconsentir los scopes nuevos. Ese fallo concreto se detecta (ver
# `_mensaje_si_scope_insuficiente`) y se traduce a un mensaje honesto, nunca un traceback.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
GMAIL_SCOPES = GOOGLE_SCOPES  # alias retrocompatible: antes solo incluía el scope de envío.

MSG_RECONECTAR_GOOGLE = (
    "Esta cuenta de Google necesita reconectarse para conceder permiso de lectura de "
    "Gmail/Calendar (pulsa «CONECTAR (OAuth)» de nuevo en Buzones)."
)


def _mensaje_si_scope_insuficiente(e_o_texto) -> str | None:
    """Si la excepción (googleapiclient.errors.HttpError) o el texto de detalle indica un 403 por
    scope insuficiente de Google (cuenta conectada ANTES de ampliar GOOGLE_SCOPES, aún con el
    scope antiguo de solo envío), devuelve el mensaje honesto para el usuario; si no, None.
    Nunca deja pasar un traceback crudo a la UI."""
    try:
        texto = str(e_o_texto).lower()
        status = getattr(getattr(e_o_texto, "resp", None), "status", None)
        es_403 = status == 403 or "403" in texto
        es_insuficiente = "insufficient" in texto or "access_token_scope" in texto
        if es_403 and es_insuficiente:
            return MSG_RECONECTAR_GOOGLE
    except Exception:
        pass
    return None


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


def _ruta_client_bundled() -> str | None:
    """Ruta del client OAuth de Google CENTRALIZADO que la app ya trae empaquetado
    (`assets/google_oauth_client.json`, un único proyecto de Google Cloud de Smart Manager
    para TODOS los clientes). Resuelta vía `src.utils.recursos.ruta_recurso` (ya consciente de
    PyInstaller/_MEIPASS — no se hand-rollea una segunda resolución de rutas). None si el
    operador de este despliegue concreto aún no ha colocado el fichero real."""
    try:
        from src.utils.recursos import ruta_recurso
        ruta = ruta_recurso("assets", "google_oauth_client.json")
    except Exception as e:
        logger.warning("Client OAuth bundled: ruta_recurso no disponible (%s); no se puede "
                       "resolver 'assets/google_oauth_client.json'.", e)
        return None
    if os.path.exists(ruta):
        logger.info("Client OAuth bundled encontrado en: %s", ruta)
        return ruta
    logger.warning("Client OAuth bundled NO encontrado. Ruta exacta consultada: %s "
                   "(coloca ahí el JSON descargado de Google Cloud Console, renombrado a "
                   "exactamente 'google_oauth_client.json').", ruta)
    return None


def _resolver_client_oauth() -> dict | None:
    """Resuelve el client OAuth de Google por PRIORIDAD (endurecimiento de seguridad +
    centralización por defecto):

      1. Variables de entorno GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET (override
         explícito del operador, p. ej. despliegues white-label con marca propia).
      2. Secret Manager (src.services.seguridad.secret_manager) — Vault/KMS futuro (mismo caso
         de uso que 1, gestionado centralmente).
      3. Client OAuth CENTRALIZADO bundled con la app (`assets/google_oauth_client.json`): el
         valor por defecto real para todos los clientes — nadie necesita ya crear su propio
         proyecto de Google Cloud ni descargar un client-secret.
      4. Fichero env GOOGLE_OAUTH_CLIENT_FILE (fallback heredado, retrocompatible).
      5. Fichero documentos/google_oauth_client.json (fallback heredado, compat. instalaciones
         antiguas — Strangler Pattern, CLAUDE.md: no se elimina un camino que funcionaba).

    Devuelve {client_id, client_secret, origen} si hay credenciales sin fichero, o
    {ruta_fichero, origen} si solo hay JSON en disco, o None si no hay configuración.
    NO se rompe ninguna instalación existente: los ficheros legacy siguen siendo fallback válido."""
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
    # 3) Client OAuth centralizado bundled con la app (valor por defecto real).
    ruta_bundled = _ruta_client_bundled()
    if ruta_bundled:
        return {"ruta_fichero": ruta_bundled, "origen": "bundled"}
    # 4 y 5) Ficheros JSON en disco (fallback heredado).
    ruta = _client_secret_path()
    if ruta:
        logger.info("Client OAuth (fallback heredado) encontrado en: %s", ruta)
        return {"ruta_fichero": ruta, "origen": "file"}
    # Nada resolvió en ningún nivel: resumen diagnóstico con TODAS las rutas consultadas, para no
    # tener que activar logging detallado por separado cuando un operador reporte "OAuth no
    # configurado" — con esto basta con mirar el log para saber exactamente qué faltaba.
    logger.warning(
        "Client OAuth de Google NO configurado en ningún nivel. Consultado: "
        "env GOOGLE_OAUTH_CLIENT_ID/SECRET (ausentes), secret manager (sin valor), "
        "bundled 'assets/google_oauth_client.json' (no encontrado), "
        "env GOOGLE_OAUTH_CLIENT_FILE=%s, 'documentos/google_oauth_client.json' (no encontrado).",
        os.getenv("GOOGLE_OAUTH_CLIENT_FILE") or "(no definida)",
    )
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
        return False, ("No se pudo iniciar la conexión con Google: la aplicación no tiene "
                       "configurado su cliente OAuth. Contacta con el soporte de Smart Manager.")
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
            flujo = InstalledAppFlow.from_client_config(client_config, GOOGLE_SCOPES)
        else:
            flujo = InstalledAppFlow.from_client_secrets_file(conf["ruta_fichero"], GOOGLE_SCOPES)
        cred = flujo.run_local_server(port=0)
        expira = cred.expiry.strftime("%Y-%m-%d %H:%M:%S") if getattr(cred, "expiry", None) else None
        correo_db.guardar_tokens(
            id_correo, "google",
            access_token=cred.token,
            refresh_token=cred.refresh_token,
            scope=" ".join(GOOGLE_SCOPES),
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
            scopes=(tok.get("scope") or "").split() or GOOGLE_SCOPES,
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
def _construir_mime(remite: str, destinatario: str, asunto: str, cuerpo: str, adjuntos, *,
                    in_reply_to: str | None = None, references: str | None = None):
    msg = MIMEMultipart()
    msg["From"] = remite
    msg["To"] = destinatario
    msg["Subject"] = asunto
    if in_reply_to:
        # Cabeceras de enhebrado (RFC 5322/2822): sin esto, el cliente del destinatario (Gmail,
        # Outlook…) muestra la respuesta como un correo SUELTO, no agrupado en el hilo original.
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.attach(MIMEText(cuerpo or "", "plain", "utf-8"))
    for ruta in (adjuntos or []):
        try:
            # Chokepoint único de lectura (petición explícita — "repositorio cifrado" de nóminas/
            # certificados): si `ruta` está cifrada en reposo, se adjunta el PDF EN CLARO, nunca el
            # blob cifrado — para cualquier otro adjunto no cifrado, esto es un no-op.
            from src.utils import cripto
            ruta_legible = cripto.resolver_ruta_legible(ruta)
            with open(ruta_legible, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            if ruta_legible != ruta:
                try:
                    os.remove(ruta_legible)
                except OSError:
                    pass
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
                     cuerpo: str = "", adjuntos=None, *,
                     in_reply_to: str | None = None, references: str | None = None) -> tuple[bool, str]:
    """Envía un documento desde el buzón corporativo indicado. Devuelve (ok, msg). `in_reply_to`/
    `references` (Message-ID del correo original) enhebran el envío como RESPUESTA real en el
    cliente del destinatario — ver `responder_correo`, que es quien normalmente los rellena."""
    c = correo_db.obtener_correo(id_correo)
    if not c:
        return False, "Buzón no encontrado."
    if c.get("estado") != "activo":
        return False, "El buzón no está activo."
    remite = c["direccion"]
    proveedor = c.get("proveedor", "simulado")
    adjuntos = adjuntos or []

    if proveedor == "google":
        ok, msg = _enviar_google(c, destinatario, asunto, cuerpo, adjuntos,
                                 in_reply_to=in_reply_to, references=references)
    elif proveedor == "smtp":
        ok, msg = _enviar_smtp(c, destinatario, asunto, cuerpo, adjuntos,
                               in_reply_to=in_reply_to, references=references)
    else:
        ok, msg = _enviar_simulado(c, destinatario, asunto, cuerpo, adjuntos,
                                   in_reply_to=in_reply_to, references=references)

    if ok:
        correo_db.marcar_sincronizacion(id_correo)
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("sistema", "CORREO_ENVIADO", "correos_corporativos",
                          f"de {remite} a {destinatario}: {asunto}")
        except Exception:
            pass
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("CORREO_ENVIADO", origen="correo", ref_entidad="correo_corporativo",
                         ref_id=id_correo,
                         payload={"de": remite, "para": destinatario, "asunto": asunto})
        except Exception:
            pass
    return ok, msg


def responder_correo(id_correo: str, id_recibido, cuerpo: str, *, asunto: str | None = None,
                     id_empresa=None) -> tuple[bool, str]:
    """Responde a un correo RECIBIDO concreto, enhebrado como respuesta real (In-Reply-To/
    References sobre su Message-ID) — a diferencia de `enviar_documento` con un destinatario
    suelto, esto reconstruye destinatario/asunto/hilo a partir del correo original, así que el
    llamador solo aporta el cuerpo de la respuesta. Usado por la automatización de respuesta
    automática de SOMA (`services.soma_delegacion`), pero es de uso general."""
    original = correo_db.obtener_recibido(id_recibido, id_empresa=id_empresa)
    if not original:
        return False, "El correo original no existe."
    if original.get("id_correo") != id_correo:
        return False, "El correo original no pertenece a este buzón."
    from email.utils import parseaddr
    _nombre, destinatario = parseaddr(original.get("remitente") or "")
    if not destinatario:
        return False, "No se pudo determinar el destinatario (remitente original ilegible)."
    asunto_original = original.get("asunto") or ""
    asunto_final = asunto or (asunto_original if asunto_original.lower().startswith("re:")
                              else f"Re: {asunto_original}")
    mid = original.get("message_id")
    return enviar_documento(id_correo, destinatario, asunto_final, cuerpo,
                            in_reply_to=mid, references=mid)


def _enviar_smtp(c: dict, destinatario, asunto, cuerpo, adjuntos, *,
                 in_reply_to=None, references=None) -> tuple[bool, str]:
    """Envío por SMTP genérico (host/puerto/credenciales del buzón). Requiere config SMTP."""
    try:
        import smtplib
        host = c.get("smtp_host"); port = int(c.get("smtp_port") or 587)
        if not host:
            return False, "SMTP no configurado en el buzón."
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos,
                               in_reply_to=in_reply_to, references=references)
        from src.utils import cripto
        pwd = cripto.descifrar_seguro(c.get("smtp_password")) or c.get("smtp_password") or ""
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            if c.get("smtp_usuario"):
                s.login(c["smtp_usuario"], pwd)
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
            mid = msg.get("Message-ID")
            ya_existia = correo_db.existe_recibido(id_correo, mid)
            if correo_db.guardar_recibido(id_correo, msg.get("From"), msg.get("Subject"),
                                          cuerpo, message_id=mid, fecha=None) and not ya_existia:
                n += 1
        srv.logout()
        correo_db.marcar_sincronizacion(id_correo)
        return n
    except Exception as e:
        logger.error("sincronizar_imap: %s", e)
        return 0


def _decodificar_cuerpo_gmail(payload: dict) -> str:
    """Extrae el texto plano (text/plain) del payload de un mensaje de la Gmail API,
    recorriendo 'parts' si el mensaje es multipart. Devuelve "" si no hay texto plano."""
    def _buscar(parte):
        if not parte:
            return ""
        body = parte.get("body", {}) or {}
        data = body.get("data")
        if parte.get("mimeType") == "text/plain" and data:
            try:
                return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "ignore")
            except Exception:
                return ""
        for sub in parte.get("parts", []) or []:
            r = _buscar(sub)
            if r:
                return r
        return ""
    texto = _buscar(payload or {})
    if not texto:
        data = ((payload or {}).get("body", {}) or {}).get("data")
        if data:
            try:
                texto = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "ignore")
            except Exception:
                texto = ""
    return texto


def sincronizar_gmail_api(id_correo: str, *, limite=20) -> tuple[int, str]:
    """Lee los últimos mensajes de la bandeja Gmail (API de SOLO LECTURA, scope gmail.readonly)
    y los persiste en correos_recibidos (idempotente por message_id, vía guardar_recibido ya
    existente). Devuelve (nº de mensajes NUEVOS guardados, mensaje para el usuario).

    Honestidad: si la cuenta está conectada con el scope antiguo (solo gmail.send, previo a
    ampliar GOOGLE_SCOPES), Google devuelve un 403 de permisos insuficientes — se traduce a un
    mensaje claro pidiendo reconectar, nunca un traceback crudo."""
    c = correo_db.obtener_correo(id_correo)
    if not c or c.get("proveedor") != "google":
        return 0, "La sincronización de Gmail solo está disponible para buzones de proveedor Google."
    cred = _credenciales_google(id_correo)
    if cred is None:
        return 0, "La cuenta de Google no está conectada (OAuth). Conéctala primero."
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=cred, cache_discovery=False)
        resp = service.users().messages().list(userId="me", maxResults=int(limite)).execute()
        n = 0
        for ref in (resp.get("messages") or []):
            msg = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            headers = {h.get("name"): h.get("value") for h in
                      ((msg.get("payload") or {}).get("headers") or [])}
            remitente = headers.get("From", "")
            asunto = headers.get("Subject", "")
            cuerpo = _decodificar_cuerpo_gmail(msg.get("payload") or {})
            mid = msg.get("id")
            ya_existia = correo_db.existe_recibido(id_correo, mid)
            if correo_db.guardar_recibido(id_correo, remitente, asunto, cuerpo,
                                          message_id=mid, fecha=None) and not ya_existia:
                n += 1
        correo_db.marcar_sincronizacion(id_correo)
        return n, f"{n} mensaje(s) nuevo(s) sincronizado(s) desde Gmail."
    except Exception as e:
        msg_scope = _mensaje_si_scope_insuficiente(e)
        if msg_scope:
            logger.warning("sincronizar_gmail_api: scope insuficiente para %s", id_correo)
            return 0, msg_scope
        logger.error("sincronizar_gmail_api: %s", e)
        return 0, f"No se pudo sincronizar Gmail: {e}"


def _enviar_google(c: dict, destinatario, asunto, cuerpo, adjuntos, *,
                   in_reply_to=None, references=None) -> tuple[bool, str]:
    cred = _credenciales_google(c["id_correo"])
    if cred is None:
        return False, "La cuenta de Google no está conectada (OAuth). Conéctala primero."
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=cred, cache_discovery=False)
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos,
                               in_reply_to=in_reply_to, references=references)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True, f"Enviado a {destinatario} desde {c['direccion']}."
    except Exception as e:
        logger.error("Error enviando por Gmail: %s", e)
        return False, f"Error al enviar por Gmail: {e}"


def _enviar_simulado(c: dict, destinatario, asunto, cuerpo, adjuntos, *,
                     in_reply_to=None, references=None) -> tuple[bool, str]:
    """No envía de verdad: guarda el .eml en disco para demostrar el flujo."""
    try:
        carpeta = os.path.join(_dir_documentos(), "correo_enviados",
                               empresa_actual_id())
        os.makedirs(carpeta, exist_ok=True)
        mime = _construir_mime(c["direccion"], destinatario, asunto, cuerpo, adjuntos,
                               in_reply_to=in_reply_to, references=references)
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
