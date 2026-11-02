"""
Webhook de Stripe para la facturación SaaS del servidor central (Fase 5). Reutiliza la verificación
de firma YA construida (`services.tpv.pagos.webhooks.stripe.verificar_firma_stripe`) y la
idempotencia YA construida (`db.pagos_webhooks.reclamar_evento`, misma tabla que usa TPV) — ningún
motor de webhooks paralelo. El evento verificado se entrega a `services.saas.billing.webhooks.
procesar_evento`, que ya sabía finalizar pago/factura/licencia (construido en una fase anterior de
este mismo proyecto de infraestructura central).

El `id_empresa` NO viaja en la URL (a diferencia de los portales B2B, pensados para invitaciones) —
se resuelve a partir del `customer` de Stripe del propio evento, contra `suscripciones.
stripe_customer_id` (columna añadida en la migración 0236): es la única correlación fiable entre
"cliente de Stripe" y "empresa" en la BD central.

Variable de entorno: `STRIPE_WEBHOOK_SECRET_SAAS` (el `whsec_...` que Stripe entrega al configurar
este endpoint en su panel). Sin ella, se rechaza cualquier evento (nunca se procesa sin verificar).
"""

import logging
import os

logger = logging.getLogger("backend_central.rutas_stripe")


def _resolver_empresa_por_customer(customer_id):
    if not customer_id:
        return None
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM suscripciones WHERE stripe_customer_id=%s LIMIT 1",
                        (customer_id,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0] if not isinstance(row, dict) else row["id_empresa"]
    except Exception as e:
        logger.error("_resolver_empresa_por_customer: %s", e)
        return None


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("stripe_central", __name__, url_prefix="/central/stripe")

    @bp.post("/webhook")
    def webhook():
        from src.services.tpv.pagos.webhooks.stripe import verificar_firma_stripe
        secreto = os.getenv("STRIPE_WEBHOOK_SECRET_SAAS")
        ok, ev = verificar_firma_stripe(dict(request.headers), request.get_data(), secreto or "")
        if not ok:
            logger.warning("Webhook Stripe rechazado: %s", ev)
            return jsonify({"ok": False, "error": ev}), 400

        evento_id = ev.get("id")
        tipo = ev.get("type") or ""
        obj = (ev.get("data") or {}).get("object") or {}
        customer_id = obj.get("customer")
        id_empresa = _resolver_empresa_por_customer(customer_id)

        from src.db.pagos_webhooks import reclamar_evento
        id_log = reclamar_evento("stripe_saas", evento_id, tipo, obj.get("id"),
                                 request.remote_addr, id_empresa=id_empresa)
        if id_log is None:
            # Duplicado/replay (Stripe reintenta si no respondemos 200 a tiempo): se acepta sin
            # reprocesar, para que Stripe deje de reintentar.
            return jsonify({"ok": True, "duplicado": True})

        if not id_empresa:
            logger.warning("Webhook Stripe: no se pudo resolver la empresa (customer=%s, evento=%s)",
                           customer_id, evento_id)
            return jsonify({"ok": True, "accion": "sin_empresa"})

        from src.services.saas.billing import webhooks as _W
        r = _W.procesar_evento(tipo, {"id_empresa": id_empresa, "ref_externa": obj.get("id")})
        logger.info("Webhook Stripe procesado: tipo=%s empresa=%s -> %s", tipo, id_empresa, r)
        return jsonify({"ok": True, **r})

    return bp
