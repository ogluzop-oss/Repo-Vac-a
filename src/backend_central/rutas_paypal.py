"""
Webhook de PayPal para la facturación SaaS del servidor central (petición explícita, 2026-11-28 —
cierra el mismo hueco que ya tenía Stripe antes de esta pieza, documentado desde el 23/11: "falta el
receptor para cobros recurrentes fallidos/cancelaciones" — pero específico de PayPal, que nunca
llegó a construirse). Cubre las suscripciones de PayPal de la web oficial (ERP, `services.
alta_comercial`) y del Plan de Pago del Portal (`services.portal_plan`) — ambas usan la MISMA
cuenta de PayPal plana de Smart Manager (`PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`), nunca el
marketplace de los portales B2B/Proveedor (ese usa Órdenes, no Suscripciones — no tiene concepto de
renovación/cancelación que vigilar vía webhook, cada pedido es un cobro puntual).

Verificación de firma MUY DISTINTA a la de Stripe (que es un HMAC local con un secreto): PayPal no
entrega un secreto de firma — cada evento se verifica con una llamada EN VIVO a su propia API
(`/v1/notifications/verify-webhook-signature`), usando el `PAYPAL_WEBHOOK_ID` (un identificador,
no un secreto) que PayPal asigna al registrar el webhook en su Dashboard. Sin `PAYPAL_WEBHOOK_ID`
configurado, se rechaza cualquier evento (nunca se procesa sin verificar).

Resolución del sujeto (ERP vs Plan de Pago del Portal) — mismo criterio que `rutas_stripe.py`:
primero se intenta resolver como empresa ERP (`altas_web_stripe.paypal_subscription_id`, tabla
compartida, resoluble sin conectar a ningún tenant); si no hay empresa, se intenta como sujeto del
Plan de Pago del Portal (`services.portal_plan.procesar_evento_webhook_paypal`). Un mismo
`paypal_subscription_id` nunca pertenece a las dos cosas a la vez.
"""

import logging
import os

logger = logging.getLogger("backend_central.rutas_paypal")

# Eventos reales de PayPal (Billing Subscriptions) traducidos al vocabulario Stripe-like que ya
# entienden `services.saas.billing.webhooks.procesar_evento` y `services.portal_plan.
# procesar_evento_webhook*` — así se reutilizan esas mismas funciones/constantes sin duplicar el
# mapeo "tipo de evento -> estado" en un tercer sitio.
_MAPEO_TIPO = {
    "PAYMENT.SALE.COMPLETED": "invoice.paid",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED": "invoice.payment_failed",
    "BILLING.SUBSCRIPTION.CANCELLED": "customer.subscription.deleted",
    "BILLING.SUBSCRIPTION.SUSPENDED": "customer.subscription.deleted",
    "BILLING.SUBSCRIPTION.EXPIRED": "customer.subscription.deleted",
}


def _paypal_base() -> str:
    return ("https://api-m.sandbox.paypal.com" if os.environ.get("PAYPAL_MODO", "test") != "live"
           else "https://api-m.paypal.com")


def _paypal_token():
    """Token OAuth2 de la cuenta de PayPal PLANA de Smart Manager — las mismas credenciales que ya
    usan `backend.sitio_oficial`/`services.alta_comercial`/`services.portal_plan` para estas
    mismas suscripciones (nunca las credenciales propias de un proveedor del marketplace B2B, que
    no tienen nada que ver con esto)."""
    import requests
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    try:
        r = requests.post(f"{_paypal_base()}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(client_id, client_secret), timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("_paypal_token (webhook) %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("_paypal_token (webhook): %s", e)
    return None


def _verificar_firma_paypal(headers: dict, body_bytes: bytes, body_json: dict) -> tuple:
    """Verifica un evento de PayPal con la API oficial (nunca localmente — PayPal no da un secreto
    de firma como Stripe). Devuelve (True, None) o (False, mensaje). Sin `PAYPAL_WEBHOOK_ID` o sin
    credenciales, rechaza siempre — nunca procesa un evento sin verificar de verdad."""
    webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        return False, "Falta PAYPAL_WEBHOOK_ID."
    token = _paypal_token()
    if not token:
        return False, "No se pudo autenticar con PayPal."
    h = {k.upper(): v for k, v in (headers or {}).items()}
    requeridas = ("PAYPAL-AUTH-ALGO", "PAYPAL-CERT-URL", "PAYPAL-TRANSMISSION-ID",
                 "PAYPAL-TRANSMISSION-SIG", "PAYPAL-TRANSMISSION-TIME")
    if not all(h.get(k) for k in requeridas):
        return False, "Faltan cabeceras de firma de PayPal."
    try:
        import requests
        payload = {
            "auth_algo": h["PAYPAL-AUTH-ALGO"],
            "cert_url": h["PAYPAL-CERT-URL"],
            "transmission_id": h["PAYPAL-TRANSMISSION-ID"],
            "transmission_sig": h["PAYPAL-TRANSMISSION-SIG"],
            "transmission_time": h["PAYPAL-TRANSMISSION-TIME"],
            "webhook_id": webhook_id,
            "webhook_event": body_json,
        }
        r = requests.post(f"{_paypal_base()}/v1/notifications/verify-webhook-signature",
                          json=payload,
                          headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"}, timeout=20)
        if r.status_code != 200:
            return False, f"PayPal {r.status_code} al verificar la firma."
        if r.json().get("verification_status") != "SUCCESS":
            return False, "Firma de PayPal no válida."
        return True, None
    except Exception as e:
        logger.error("_verificar_firma_paypal: %s", e)
        return False, "Error interno verificando la firma."


def _resolver_empresa_y_config_por_paypal_subscription(subscription_id):
    """Equivalente de `rutas_stripe._resolver_empresa_y_config_por_customer`, por
    `paypal_subscription_id` en vez de `stripe_customer_id` — mismas 3 empresas de antes del
    aislamiento (sin fila en `tenants_db`) caen igual en el fallback de la base compartida."""
    if not subscription_id:
        return None, None
    from src.db.conexion import obtener_conexion
    id_empresa = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM altas_web_stripe WHERE paypal_subscription_id=%s "
                       "ORDER BY id DESC LIMIT 1", (subscription_id,))
            row = cur.fetchone()
            if row:
                id_empresa = row[0] if not isinstance(row, dict) else row["id_empresa"]
    except Exception as e:
        logger.error("_resolver_empresa_y_config_por_paypal_subscription (altas_web_stripe): %s", e)
    if not id_empresa:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id_empresa FROM suscripciones WHERE paypal_subscription_id=%s "
                           "LIMIT 1", (subscription_id,))
                row = cur.fetchone()
                if row:
                    id_empresa = row[0] if not isinstance(row, dict) else row["id_empresa"]
        except Exception as e:
            logger.error("_resolver_empresa_y_config_por_paypal_subscription (suscripciones): %s", e)
    if not id_empresa:
        return None, None
    try:
        from src.services import provisioning
        cfg = provisioning.config_tenant(id_empresa)
    except Exception as e:
        logger.error("_resolver_empresa_y_config_por_paypal_subscription (config_tenant, %s): %s",
                     id_empresa, e)
        cfg = None
    return id_empresa, cfg


def _subscription_id_de(obj: dict) -> str | None:
    """El identificador de la Suscripción viene en campos distintos según el evento: `resource.id`
    para los eventos `BILLING.SUBSCRIPTION.*` (el propio `resource` ES la suscripción);
    `resource.billing_agreement_id` para `PAYMENT.SALE.COMPLETED` (el propio pago de un ciclo de
    facturación, que referencia a la suscripción que lo originó)."""
    return obj.get("billing_agreement_id") or obj.get("id")


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("paypal_central", __name__, url_prefix="/central/paypal")

    @bp.post("/webhook")
    def webhook():
        body_bytes = request.get_data()
        try:
            import json
            body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return jsonify({"ok": False, "error": "Cuerpo JSON no válido."}), 400

        ok, mensaje = _verificar_firma_paypal(dict(request.headers), body_bytes, body_json)
        if not ok:
            logger.warning("Webhook PayPal rechazado: %s", mensaje)
            return jsonify({"ok": False, "error": mensaje}), 400

        evento_id = body_json.get("id")
        tipo_paypal = body_json.get("event_type") or ""
        obj = body_json.get("resource") or {}
        subscription_id = _subscription_id_de(obj)

        from src.db.pagos_webhooks import reclamar_evento
        id_empresa, cfg_tenant = _resolver_empresa_y_config_por_paypal_subscription(subscription_id)
        id_log = reclamar_evento("paypal_saas", evento_id, tipo_paypal, subscription_id,
                                 request.remote_addr, id_empresa=id_empresa)
        if id_log is None:
            return jsonify({"ok": True, "duplicado": True})

        tipo_mapeado = _MAPEO_TIPO.get(tipo_paypal)
        if not tipo_mapeado:
            logger.info("Webhook PayPal ignorado (tipo no vigilado): %s", tipo_paypal)
            return jsonify({"ok": True, "accion": "ignorado", "tipo": tipo_paypal})

        if id_empresa:
            from src.services.saas.billing import webhooks as _W
            r = _W.procesar_evento(
                tipo_mapeado, {"id_empresa": id_empresa, "ref_externa": subscription_id,
                              "proximo_cobro": None}, config=cfg_tenant)
            logger.info("Webhook PayPal procesado (ERP): tipo=%s empresa=%s -> %s",
                       tipo_paypal, id_empresa, r)
            return jsonify({"ok": True, **r})

        from src.services import portal_plan as _PP
        r_portal = _PP.procesar_evento_webhook_paypal(tipo_mapeado, subscription_id)
        if r_portal.get("ok") or r_portal.get("accion") not in ("sin_sujeto", "ignorado"):
            logger.info("Webhook PayPal (Plan de Pago del Portal): tipo=%s subscription=%s -> %s",
                       tipo_paypal, subscription_id, r_portal)
            return jsonify({"ok": True, **r_portal})
        logger.warning("Webhook PayPal: no se pudo resolver el sujeto (subscription=%s, evento=%s)",
                       subscription_id, evento_id)
        return jsonify({"ok": True, "accion": "sin_empresa"})

    return bp
