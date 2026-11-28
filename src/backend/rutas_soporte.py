"""
Buzón de sugerencias/incidencias del escritorio → Smart Manager (petición explícita, 2026-11-16).

La app de escritorio NUNCA tiene credenciales SMTP propias de Smart Manager (serían credenciales
del desarrollador embebidas en un `.exe` distribuido a cada cliente — inaceptable). Por eso este
endpoint vive aquí, en el backend del VPS, que ya reutiliza el mismo envío SMTP directo que
`sitio_oficial._enviar_codigo_por_email`/`compras.b2b_onboarding._enviar_email` (mismas variables
de entorno `SMTP_*`, mismo criterio: degrada honestamente, nunca finge un envío que no ocurrió).
Mismo patrón defensivo que `licencia_central.cliente` del lado del escritorio: la llamada HTTP sale
con timeout corto y nunca bloquea la UI si no hay red/servidor.

Sin autenticación de usuario (no hay sesión de cliente que verificar aquí — es un formulario de
feedback, no un dato sensible de la empresa); se limita el tamaño de los campos para evitar abuso
evidente (payloads gigantes), sin inventar un motor de rate-limiting que no se ha pedido.
"""

import logging
import os

logger = logging.getLogger("backend.rutas_soporte")

_DESTINATARIO = "smart.manager.enterprises@gmail.com"
_MAX_ASUNTO = 200
_MAX_DESCRIPCION = 5000
_MAX_EMPRESA = 200


def _enviar_email_soporte(asunto, descripcion, empresa, email_contacto) -> bool:
    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.info("SMTP no configurado: no se envía la sugerencia/incidencia (asunto=%r).", asunto)
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        remitente = os.environ.get("SMTP_FROM", _DESTINATARIO)
        cuerpo = (
            f"Nueva sugerencia/incidencia recibida desde el Buzón de Sugerencias del escritorio.\n\n"
            f"Empresa: {empresa or '(no indicada)'}\n"
            f"Contacto: {email_contacto or '(no indicado)'}\n\n"
            f"Asunto: {asunto}\n\n"
            f"Descripción:\n{descripcion}\n")
        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = f"[Buzón de sugerencias] {asunto}"
        msg["From"] = remitente
        msg["To"] = _DESTINATARIO
        if email_contacto:
            msg["Reply-To"] = email_contacto

        puerto = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, puerto, timeout=10) as s:
            s.starttls()
            usuario_smtp = os.environ.get("SMTP_USER")
            password_smtp = os.environ.get("SMTP_PASSWORD")
            if usuario_smtp and password_smtp:
                s.login(usuario_smtp, password_smtp)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error("_enviar_email_soporte: %s", e)
        return False


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("soporte", __name__, url_prefix="/soporte")

    @bp.post("/buzon")
    def buzon():
        datos = request.get_json(silent=True) or {}
        asunto = (datos.get("asunto") or "").strip()[:_MAX_ASUNTO]
        descripcion = (datos.get("descripcion") or "").strip()[:_MAX_DESCRIPCION]
        empresa = (datos.get("empresa") or "").strip()[:_MAX_EMPRESA]
        email_contacto = (datos.get("email_contacto") or "").strip()[:_MAX_EMPRESA]
        if not asunto or not descripcion:
            return jsonify({"ok": False, "error": "Faltan el asunto o la descripción."}), 400

        if _enviar_email_soporte(asunto, descripcion, empresa, email_contacto):
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "No se pudo enviar (servicio de correo no "
                                              "disponible en este momento)."}), 502

    return bp
