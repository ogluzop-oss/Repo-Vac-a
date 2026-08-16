"""
Webhooks de Stripe Connect (F3 — Marketplace + Pagos).

Reutiliza la infraestructura de webhooks existente:
- verificación de firma HMAC + replay: `services.tpv.pagos.webhooks.stripe.verificar_firma_stripe`,
- idempotencia por evento: `db.pagos_webhooks` (`reclamar_evento`/`actualizar_evento`),
- credenciales cifradas por empresa: `db.pagos` (`pasarela_config`).

A diferencia del webhook de checkout (que mueve `pedidos_online`), este despacha eventos de MARKETPLACE:
- `account.updated`  → sincroniza el estado KYB de la cuenta conectada (`cuentas.sincronizar_estado`),
- `payment_intent.amount_capturable_updated` → confirma la retención (FUNDS_HELD),
- `payment_intent.succeeded` / `charge.captured` → confirma la liberación (FUNDS_RELEASED),
- `charge.dispute.created` → abre disputa (IN_DISPUTE),
- `charge.refunded` / `refund.updated` / `payment_intent.canceled` → REFUNDED.

Las transiciones dirigidas por webhook son LOCALES (no vuelven a llamar al PSP): el PSP ya ejecutó la
operación; aquí solo se refleja el estado (idempotente, sin revertir estados terminales).
"""

import hashlib
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID

logger = logging.getLogger("pagos_marketplace.webhooks")


def procesar_webhook_connect(headers, body, id_empresa=None) -> dict:
    """Punto de entrada (independiente del transporte). Devuelve {ok, http, accion, duplicado, mensaje}."""
    id_empresa = id_empresa or EMPRESA_DEFAULT_ID
    from src.db import pagos as pagos_db
    from src.db import pagos_webhooks as wlog
    from src.services.tpv.pagos.webhooks.stripe import verificar_firma_stripe

    cfg = pagos_db.obtener_config(id_empresa) or {}
    secret = cfg.get("webhook_secret_connect") or cfg.get("webhook_secret") or ""
    ok, ev = verificar_firma_stripe(headers or {}, body or b"", secret)
    if not ok:
        logger.warning("Webhook Connect rechazado (empresa %s): %s", id_empresa, ev)
        return {"ok": False, "http": 400, "mensaje": ev}

    tipo = ev.get("type") or ""
    obj = (ev.get("data") or {}).get("object") or {}
    evento_id = ev.get("id")
    if not evento_id:
        evento_id = "auto-" + hashlib.sha256(f"{tipo}|{obj.get('id')}".encode()).hexdigest()[:32]

    id_log = wlog.reclamar_evento("stripe_connect", evento_id, evento_tipo=tipo,
                                  referencia=obj.get("id"), id_empresa=id_empresa)
    if id_log is None:
        return {"ok": True, "http": 200, "duplicado": True, "mensaje": "Evento duplicado (ignorado)."}

    res = _despachar(tipo, obj, id_empresa)
    try:
        wlog.actualizar_evento(id_log, estado=res.get("estado"), resultado=res.get("accion"),
                               evento_tipo=tipo)
    except Exception as e:
        logger.debug("actualizar_evento: %s", e)
    return {"ok": True, "http": 200, "accion": res.get("accion"), "detalle": res.get("detalle"),
            "duplicado": False, "mensaje": "Procesado."}


def _despachar(tipo, obj, id_empresa) -> dict:
    from src.services.pagos_marketplace import cuentas, escrow

    if tipo == "account.updated":
        acct = obj.get("id")
        payouts = bool(obj.get("payouts_enabled"))
        charges = bool(obj.get("charges_enabled"))
        disabled = (obj.get("requirements") or {}).get("disabled_reason")
        status = "verified" if payouts else ("restricted" if disabled else "pending")
        ext = ((obj.get("external_accounts") or {}).get("data") or [])
        banco = ext[0].get("bank_name") if ext else None
        ultimos4 = ext[0].get("last4") if ext else None
        cuentas.sincronizar_estado(acct, status=status, payouts_enabled=payouts, charges_enabled=charges,
                                   banco=banco, ultimos4=ultimos4)
        return {"accion": "account_synced", "detalle": acct, "estado": status}

    # Eventos ligados a un PaymentIntent → localiza la transacción por su referencia de pago.
    pi = obj.get("payment_intent") or (obj.get("id") if tipo.startswith("payment_intent") else None)
    tx = escrow.tx_por_payment_ref(pi) if pi else None

    if tipo == "payment_intent.amount_capturable_updated":
        if tx:
            escrow.set_estado_local(tx["id"], "FUNDS_HELD", motivo="pi_capturable")
        return {"accion": "funds_held", "detalle": pi, "estado": "FUNDS_HELD"}
    if tipo in ("payment_intent.succeeded", "charge.captured"):
        if tx:
            escrow.set_estado_local(tx["id"], "FUNDS_RELEASED", motivo=tipo)
        return {"accion": "funds_released", "detalle": pi, "estado": "FUNDS_RELEASED"}
    if tipo == "charge.dispute.created":
        if tx:
            escrow.set_estado_local(tx["id"], "IN_DISPUTE", motivo="dispute")
        return {"accion": "dispute_opened", "detalle": pi, "estado": "IN_DISPUTE"}
    if tipo in ("charge.refunded", "refund.updated", "payment_intent.canceled"):
        if tx:
            escrow.set_estado_local(tx["id"], "REFUNDED", motivo=tipo)
        return {"accion": "refunded", "detalle": pi, "estado": "REFUNDED"}

    return {"accion": "ignored", "detalle": tipo, "estado": None}
