"""
Webhook de Stripe para la facturación SaaS del servidor central (Fase 5). Reutiliza la verificación
de firma YA construida (`services.tpv.pagos.webhooks.stripe.verificar_firma_stripe`) y la
idempotencia YA construida (`db.pagos_webhooks.reclamar_evento`, misma tabla que usa TPV) — ningún
motor de webhooks paralelo. El evento verificado se entrega a `services.saas.billing.webhooks.
procesar_evento`, que ya sabía finalizar pago/factura/licencia (construido en una fase anterior de
este mismo proyecto de infraestructura central).

El `id_empresa` NO viaja en la URL (a diferencia de los portales B2B, pensados para invitaciones) —
se resuelve a partir del `customer` de Stripe del propio evento. CORRECCIÓN (hallazgo real,
2026-11-16): desde que cada empresa SaaS nueva vive en su PROPIA base de datos física aislada
(migr. 0340, `services.provisioning.aprovisionar_tenant_nuevo`), ya NO basta con mirar
`suscripciones.stripe_customer_id` en la base compartida — esa columna, para cualquier empresa
dada de alta tras el aislamiento, solo existe en SU base física, nunca en la compartida (el
webhook nunca encontraba la empresa, los eventos reales de Stripe no se aplicaban nunca). Ahora se
resuelve primero contra `altas_web_stripe.stripe_customer_id` (migr. 0344, en la base compartida,
igual que `cuentas_web_central`/`tenants_db` — resoluble SIN conectar a ningún tenant) y, con el
`id_empresa` ya conocido, `services.provisioning.config_tenant` da la base física correcta donde
aplicar el evento. Las 3 empresas de ANTES del aislamiento (sin fila en `tenants_db`) siguen
cayendo en el fallback de siempre (`suscripciones.stripe_customer_id` en la compartida,
`config=None`) — comportamiento idéntico al de antes para ellas.

Variable de entorno: `STRIPE_WEBHOOK_SECRET_SAAS` (el `whsec_...` que Stripe entrega al configurar
este endpoint en su panel). Sin ella, se rechaza cualquier evento (nunca se procesa sin verificar).
"""

import logging
import os

logger = logging.getLogger("backend_central.rutas_stripe")


def _resolver_empresa_y_config_por_customer(customer_id):
    """Devuelve (id_empresa, config) o (None, None). `config` es el dict de conexión a la base
    física del tenant (`services.provisioning.config_tenant`), o `None` si la empresa sigue en la
    base compartida (de antes del aislamiento, o no resuelta)."""
    if not customer_id:
        return None, None
    from src.db.conexion import obtener_conexion
    id_empresa = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM altas_web_stripe WHERE stripe_customer_id=%s "
                       "ORDER BY id DESC LIMIT 1", (customer_id,))
            row = cur.fetchone()
            if row:
                id_empresa = row[0] if not isinstance(row, dict) else row["id_empresa"]
    except Exception as e:
        logger.error("_resolver_empresa_y_config_por_customer (altas_web_stripe): %s", e)
    if not id_empresa:
        # Fallback: empresas de antes del aislamiento por tenant, cuyo stripe_customer_id vive
        # directamente en `suscripciones` de la base compartida.
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id_empresa FROM suscripciones WHERE stripe_customer_id=%s "
                           "LIMIT 1", (customer_id,))
                row = cur.fetchone()
                if row:
                    id_empresa = row[0] if not isinstance(row, dict) else row["id_empresa"]
        except Exception as e:
            logger.error("_resolver_empresa_y_config_por_customer (suscripciones): %s", e)
    if not id_empresa:
        return None, None
    try:
        from src.services import provisioning
        cfg = provisioning.config_tenant(id_empresa)
    except Exception as e:
        logger.error("_resolver_empresa_y_config_por_customer (config_tenant, %s): %s",
                     id_empresa, e)
        cfg = None
    return id_empresa, cfg


def _proximo_cobro_de_invoice(obj):
    """Fecha REAL del próximo cobro/renovación (petición explícita, 2026-11-16: mostrarla exacta
    en la web/escritorio) — se lee del propio evento `invoice.paid` de Stripe, nunca se calcula a
    mano (evita que se desincronice de lo que Stripe cobra de verdad). `period_end` del Invoice (o,
    si faltara, el de su primera línea) es el fin del periodo que ACABA de cobrarse — coincide con
    la fecha del SIGUIENTE cobro en una suscripción recurrente estándar."""
    import datetime as _dt
    ts = obj.get("period_end")
    if not ts:
        lineas = (obj.get("lines") or {}).get("data") or []
        if lineas:
            ts = (lineas[0].get("period") or {}).get("end")
    if not ts:
        return None
    try:
        return _dt.date.fromtimestamp(int(ts))
    except Exception:
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
        id_empresa, cfg_tenant = _resolver_empresa_y_config_por_customer(customer_id)

        from src.db.pagos_webhooks import reclamar_evento
        id_log = reclamar_evento("stripe_saas", evento_id, tipo, obj.get("id"),
                                 request.remote_addr, id_empresa=id_empresa)
        if id_log is None:
            # Duplicado/replay (Stripe reintenta si no respondemos 200 a tiempo): se acepta sin
            # reprocesar, para que Stripe deje de reintentar.
            return jsonify({"ok": True, "duplicado": True})

        if not id_empresa:
            # Plan de Pago del Portal B2B/Proveedor (petición explícita, 2026-11-27 — cierra el
            # hueco de renovación/cancelación que quedaba pendiente, ver `services.portal_plan`):
            # este customer de Stripe puede no ser de ninguna empresa ERP y SÍ de un sujeto del
            # portal (`portal_suscripciones`, tabla y resolución totalmente independientes de las
            # de arriba — un mismo `customer_id` nunca pertenece a las dos cosas a la vez). Mismo
            # endpoint/secreto de Stripe, sin un segundo webhook que mantener.
            from src.services import portal_plan as _PP
            r_portal = _PP.procesar_evento_webhook(tipo, customer_id)
            if r_portal.get("ok") or r_portal.get("accion") not in ("sin_sujeto", "ignorado"):
                logger.info("Webhook Stripe (Plan de Pago del Portal): tipo=%s customer=%s -> %s",
                           tipo, customer_id, r_portal)
                return jsonify({"ok": True, **r_portal})
            logger.warning("Webhook Stripe: no se pudo resolver la empresa (customer=%s, evento=%s)",
                           customer_id, evento_id)
            return jsonify({"ok": True, "accion": "sin_empresa"})

        from src.services.saas.billing import webhooks as _W
        r = _W.procesar_evento(
            tipo, {"id_empresa": id_empresa, "ref_externa": obj.get("id"),
                  "proximo_cobro": _proximo_cobro_de_invoice(obj)},
            config=cfg_tenant)
        logger.info("Webhook Stripe procesado: tipo=%s empresa=%s -> %s", tipo, id_empresa, r)
        return jsonify({"ok": True, **r})

    return bp
