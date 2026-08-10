"""
Omnichannel Platform (CCP Fase II · B8) — canales reales DEGRADABLES.

WhatsApp, SMS, Push, Teams, Slack, Telegram y Firma Electrónica implementan `CanalComunicacion`.
Envío REAL solo si hay credenciales configuradas (env o secret_manager); si no, `disponible()`=False y
`enviar()` devuelve `no_operativo` (mismo patrón que email/pagos/fiscal simulados del ERP). Sin
dependencias duras nuevas: `requests` (ya presente) por importación perezosa. El Corporate
Communication Service NO se toca: sigue siendo el único punto de entrada.
"""

import logging
import os

from src.services.ccp.canales import registrar_canal
from src.services.ccp.canales.base import CanalComunicacion
from src.services.ccp.modelo import (
    CANAL_FIRMA, CANAL_PUSH, CANAL_SLACK, CANAL_SMS, CANAL_TEAMS, CANAL_TELEGRAM, CANAL_WHATSAPP,
    ESTADO_ENVIADO, ESTADO_FALLIDO, ESTADO_NO_OPERATIVO, Resultado,
)

logger = logging.getLogger("ccp.omnichannel")


def _secreto(nombre):
    """Lee una credencial de entorno o del secret manager (degradable)."""
    v = os.getenv(nombre)
    if v:
        return v
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.obtener_secreto(nombre)
    except Exception:
        return None


class CanalDegradable(CanalComunicacion):
    """Canal real solo si está configurado; si no, no operativo. Nunca lanza dependencias duras."""
    requiere = ()   # nombres de credenciales necesarias

    def _config(self) -> dict:
        cfg = {k: _secreto(k) for k in self.requiere}
        return cfg if all(cfg.values()) else {}

    def disponible(self) -> bool:
        return bool(self._config())

    def enviar(self, comunicacion) -> Resultado:
        com_id = getattr(comunicacion, "com_id", None)
        cfg = self._config()
        if not cfg:
            return Resultado(ok=False, canal=self.clave, com_id=com_id, estado=ESTADO_NO_OPERATIVO,
                             mensaje=f"Canal '{self.clave}' preparado; sin credenciales configuradas.")
        try:
            return self._enviar_real(comunicacion, cfg)
        except Exception as e:
            logger.error("%s envío real: %s", self.clave, e)
            return Resultado(ok=False, canal=self.clave, com_id=com_id, estado=ESTADO_FALLIDO,
                             mensaje=f"Error de envío por {self.clave}: {e}")

    def _enviar_real(self, comunicacion, cfg) -> Resultado:
        raise NotImplementedError

    def _ok(self, comunicacion, msg="enviado"):
        return Resultado(ok=True, canal=self.clave, com_id=getattr(comunicacion, "com_id", None),
                         estado=ESTADO_ENVIADO, mensaje=msg)


class WhatsAppChannel(CanalDegradable):
    clave = CANAL_WHATSAPP; nombre = "WhatsApp Business"
    requiere = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID")

    def _enviar_real(self, com, cfg):
        import requests
        url = f"https://graph.facebook.com/v20.0/{cfg['WHATSAPP_PHONE_ID']}/messages"
        r = requests.post(url, timeout=20, headers={"Authorization": f"Bearer {cfg['WHATSAPP_TOKEN']}"},
                          json={"messaging_product": "whatsapp", "to": com.destinatario_principal(),
                                "type": "text", "text": {"body": com.cuerpo or com.asunto}})
        return self._ok(com, f"WhatsApp {r.status_code}") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"WhatsApp {r.status_code}")


class SmsChannel(CanalDegradable):
    clave = CANAL_SMS; nombre = "SMS"
    requiere = ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM")

    def _enviar_real(self, com, cfg):
        import requests
        url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg['TWILIO_SID']}/Messages.json"
        r = requests.post(url, timeout=20, auth=(cfg["TWILIO_SID"], cfg["TWILIO_TOKEN"]),
                          data={"From": cfg["TWILIO_FROM"], "To": com.destinatario_principal(),
                                "Body": com.cuerpo or com.asunto})
        return self._ok(com, "SMS enviado") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"SMS {r.status_code}")


class TelegramChannel(CanalDegradable):
    clave = CANAL_TELEGRAM; nombre = "Telegram"
    requiere = ("TELEGRAM_BOT_TOKEN",)

    def _enviar_real(self, com, cfg):
        import requests
        chat = (com.metadatos or {}).get("chat_id") or com.destinatario_principal()
        url = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendMessage"
        r = requests.post(url, timeout=20, json={"chat_id": chat, "text": com.cuerpo or com.asunto})
        return self._ok(com, "Telegram enviado") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"Telegram {r.status_code}")


class PushChannel(CanalDegradable):
    clave = CANAL_PUSH; nombre = "Notificaciones Push"
    requiere = ("FCM_SERVER_KEY",)

    def _enviar_real(self, com, cfg):
        import requests
        r = requests.post("https://fcm.googleapis.com/fcm/send", timeout=20,
                          headers={"Authorization": f"key={cfg['FCM_SERVER_KEY']}"},
                          json={"to": com.destinatario_principal(),
                                "notification": {"title": com.asunto, "body": com.cuerpo}})
        return self._ok(com, "Push enviado") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"Push {r.status_code}")


class _WebhookChannel(CanalDegradable):
    """Teams/Slack por Incoming Webhook (una sola credencial: la URL)."""
    def _enviar_real(self, com, cfg):
        import requests
        url = list(cfg.values())[0]
        r = requests.post(url, timeout=20, json={"text": f"*{com.asunto}*\n{com.cuerpo}"})
        return self._ok(com, f"{self.nombre} enviado") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"{self.nombre} {r.status_code}")


class TeamsChannel(_WebhookChannel):
    clave = CANAL_TEAMS; nombre = "Microsoft Teams"; requiere = ("TEAMS_WEBHOOK_URL",)


class SlackChannel(_WebhookChannel):
    clave = CANAL_SLACK; nombre = "Slack"; requiere = ("SLACK_WEBHOOK_URL",)


class FirmaChannel(CanalDegradable):
    clave = CANAL_FIRMA; nombre = "Firma Electrónica"; requiere = ("FIRMA_API_KEY", "FIRMA_API_URL")

    def _enviar_real(self, com, cfg):
        import requests
        r = requests.post(cfg["FIRMA_API_URL"], timeout=30,
                          headers={"Authorization": f"Bearer {cfg['FIRMA_API_KEY']}"},
                          json={"email": com.destinatario_principal(), "subject": com.asunto,
                                "document": (com.adjuntos or [None])[0]})
        return self._ok(com, "Firma solicitada") if r.ok else \
            Resultado(ok=False, canal=self.clave, com_id=com.com_id, estado=ESTADO_FALLIDO,
                      mensaje=f"Firma {r.status_code}")


for _c in (WhatsAppChannel(), SmsChannel(), TelegramChannel(), PushChannel(), TeamsChannel(),
           SlackChannel(), FirmaChannel()):
    registrar_canal(_c)
