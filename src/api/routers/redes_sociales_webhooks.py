"""
Router /webhooks — receptor de eventos en tiempo real de plataformas sociales. SIN
`requiere_auth` (el llamador es la plataforma externa, no un usuario de Smart Manager): la
seguridad es la verificación de firma/token propia de cada plataforma, no nuestro JWT.

Meta (Instagram + Facebook/Messenger): protocolo de verificación GET (`hub.mode`/`hub.verify_token`
/`hub.challenge`, documentado por Meta) + firma HMAC-SHA256 del cuerpo en `X-Hub-Signature-256`
contra `META_APP_SECRET`. Sin `META_WEBHOOK_VERIFY_TOKEN`/`META_APP_SECRET` configurados, el
endpoint existe pero rechaza (403) — degradación honesta, nunca acepta sin verificar.
"""

import hashlib
import hmac
import logging
import os

logger = logging.getLogger("api.redes_sociales_webhooks")


def _firma_meta_valida(cuerpo_raw: bytes, cabecera_firma: str) -> bool:
    secreto = os.getenv("META_APP_SECRET")
    if not secreto or not cabecera_firma:
        return False
    esperado = "sha256=" + hmac.new(secreto.encode("utf-8"), cuerpo_raw,
                                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecera_firma)


def registrar(bp):
    @bp.get("/webhooks/meta")
    def webhook_meta_verificar():
        from flask import request
        verify_token = os.getenv("META_WEBHOOK_VERIFY_TOKEN")
        if (verify_token and request.args.get("hub.mode") == "subscribe" and
                request.args.get("hub.verify_token") == verify_token):
            return request.args.get("hub.challenge", ""), 200
        return "verify_token inválido o no configurado", 403

    @bp.post("/webhooks/meta")
    def webhook_meta_recibir():
        from flask import jsonify, request
        firma = request.headers.get("X-Hub-Signature-256", "")
        if not _firma_meta_valida(request.get_data() or b"", firma):
            logger.warning("webhook meta: firma inválida o META_APP_SECRET no configurado")
            return jsonify({"error": "firma inválida"}), 403
        payload = request.get_json(silent=True) or {}
        from src.services.redes_sociales import inbox
        r = inbox.ingerir_webhook_meta(payload)
        # Meta exige 200 siempre que el payload se haya podido procesar (aunque no haya datos
        # nuevos) para no reintentar entregas indefinidamente.
        return jsonify(r), 200
