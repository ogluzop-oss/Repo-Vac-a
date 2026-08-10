"""
Canales PREPARADOS de la CCP — existen arquitectónicamente pero SIN funcionalidad real.

WhatsApp, SMS, Push, Microsoft Teams, Slack y Firma Electrónica quedan registrados como canales para
que la plataforma sea multicanal desde el diseño, pero `disponible()` es False y `enviar()` no realiza
ningún envío real (devuelve estado 'no_operativo'). Implementar uno en el futuro = sustituir su clase
por una versión operativa, sin tocar el resto de la CCP.
"""

from src.services.ccp.canales import registrar_canal
from src.services.ccp.canales.base import CanalPreparado
from src.services.ccp.modelo import (
    CANAL_FIRMA, CANAL_PUSH, CANAL_SLACK, CANAL_SMS, CANAL_TEAMS, CANAL_WHATSAPP,
)


class WhatsAppChannel(CanalPreparado):
    clave = CANAL_WHATSAPP
    nombre = "WhatsApp Business"


class SmsChannel(CanalPreparado):
    clave = CANAL_SMS
    nombre = "SMS"


class PushChannel(CanalPreparado):
    clave = CANAL_PUSH
    nombre = "Notificaciones Push"


class TeamsChannel(CanalPreparado):
    clave = CANAL_TEAMS
    nombre = "Microsoft Teams"


class SlackChannel(CanalPreparado):
    clave = CANAL_SLACK
    nombre = "Slack"


class FirmaChannel(CanalPreparado):
    clave = CANAL_FIRMA
    nombre = "Firma Electrónica"


for _c in (WhatsAppChannel(), SmsChannel(), PushChannel(), TeamsChannel(), SlackChannel(),
           FirmaChannel()):
    registrar_canal(_c)
