"""
Cliente REAL de Stripe para la facturación SaaS (Fase 5, ver plan `hazy-riding-aurora`). SOLO
domiciliación SEPA (Direct Debit): encaja con el IBAN que la empresa ya introduce en el módulo
Suscripción (`services.saas.suscripciones.guardar_iban`, cifrado con `utils.cripto`) y no requiere
ningún flujo de pago en el navegador (Stripe Elements/Checkout) — inviable de abrir de forma nativa
desde una app de escritorio PyQt6 sin salir de la aplicación. El cobro con tarjeta NO está
implementado por el mismo motivo; queda para cuando exista un flujo web de alta (Fase 4 lo tiene
para el fundador, no para el cliente final).

El mandato SEPA se crea "offline" (`mandate_data.customer_acceptance.type=offline`): Stripe permite
este modo cuando el mandato real ya se ha recogido por otra vía — aquí, al domiciliar el IBAN dentro
del alta/contrato de la suscripción. Que ese contrato constituya un mandato SEPA válido es
responsabilidad legal del titular del negocio, no de este código.

IMPORTANTE (honestidad): en el momento de escribir esto NO existe todavía una cuenta de Stripe (ni
siquiera de pruebas) para validar contra la API real — este módulo está completo y listo, pero NUNCA
se ha ejecutado contra Stripe de verdad. Antes de fiarse de él con dinero real, hay que probarlo
contra el modo de pruebas (test mode, alta gratuita e instantánea, sin verificación de negocio).

`STRIPE_SECRET_KEY` (env var) activa el proveedor; sin ella, `cobrar()` devuelve "no_configurado"
(igual que el resto de proveedores no configurados de `billing/base.py`).
"""

import logging
import os

logger = logging.getLogger("saas.billing.stripe_gateway")


class _SinMetodoPago(Exception):
    pass


def _api_key():
    return os.getenv("STRIPE_SECRET_KEY")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _suscripcion_de(id_empresa):
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM suscripciones WHERE id_empresa=%s ORDER BY id DESC LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        return _fila(cur, r) if r else None


def _guardar_ids_stripe(id_suscripcion, *, customer_id=None, payment_method_id=None):
    from src.db.conexion import obtener_conexion
    sets, params = [], []
    if customer_id:
        sets.append("stripe_customer_id=%s"); params.append(customer_id)
    if payment_method_id:
        sets.append("stripe_payment_method_id=%s"); params.append(payment_method_id)
    if not sets:
        return
    params.append(id_suscripcion)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE suscripciones SET {', '.join(sets)} WHERE id=%s", params)
        conn.commit()


def _nombre_empresa(id_empresa):
    try:
        from src.db.empresa import obtener_empresa
        emp = obtener_empresa(id_empresa)
        return (emp or {}).get("nombre_empresa") or id_empresa
    except Exception:
        return id_empresa


def _asegurar_cliente_y_metodo(stripe, id_empresa, sus):
    """Crea (si faltan) el Customer y el PaymentMethod SEPA de Stripe para esta suscripción, a
    partir del IBAN ya domiciliado. Devuelve (customer_id, payment_method_id, es_metodo_nuevo).
    Lanza `_SinMetodoPago` si la empresa no tiene IBAN domiciliado y tampoco tiene ya un método
    guardado de una vez anterior."""
    customer_id = sus.get("stripe_customer_id")
    if not customer_id:
        cliente = stripe.Customer.create(name=_nombre_empresa(id_empresa),
                                         metadata={"id_empresa": id_empresa})
        customer_id = cliente["id"]
        _guardar_ids_stripe(sus["id"], customer_id=customer_id)

    payment_method_id = sus.get("stripe_payment_method_id")
    if payment_method_id:
        return customer_id, payment_method_id, False

    iban_cifrado = sus.get("iban_cifrado")
    if not iban_cifrado:
        raise _SinMetodoPago()
    from src.utils import cripto
    iban = cripto.descifrar(iban_cifrado)
    if not iban:
        raise _SinMetodoPago()

    metodo = stripe.PaymentMethod.create(
        type="sepa_debit",
        sepa_debit={"iban": iban},
        billing_details={"name": _nombre_empresa(id_empresa)},
    )
    stripe.PaymentMethod.attach(metodo["id"], customer=customer_id)
    _guardar_ids_stripe(sus["id"], payment_method_id=metodo["id"])
    return customer_id, metodo["id"], True


def cobrar(importe, *, referencia=None, id_empresa=None) -> dict:
    """Cobro real vía SEPA Direct Debit. Devuelve el mismo contrato que el resto de
    `BillingProvider`s ({ok, estado, ref_externa, proveedor}), con un tercer estado adicional
    "procesando" — SEPA no confirma en el acto (tarda de 2 a 14 días hábiles); la confirmación
    definitiva llega más tarde por el webhook (`billing.webhooks.procesar_evento`, ya construido),
    nunca se da por buena de inmediato (ver Fiscal/AEAT en CLAUDE.md: nunca simular un pago aceptado
    antes de que el proveedor lo confirme de verdad)."""
    if not _api_key():
        return {"ok": False, "estado": "no_configurado", "proveedor": "stripe"}
    if not id_empresa:
        return {"ok": False, "estado": "sin_empresa", "proveedor": "stripe"}
    sus = _suscripcion_de(id_empresa)
    if not sus:
        return {"ok": False, "estado": "sin_suscripcion", "proveedor": "stripe"}

    try:
        import stripe
        stripe.api_key = _api_key()
    except Exception as e:
        logger.error("import stripe: %s", e)
        return {"ok": False, "estado": "no_configurado", "proveedor": "stripe"}

    try:
        customer_id, payment_method_id, es_nuevo = _asegurar_cliente_y_metodo(stripe, id_empresa, sus)
    except _SinMetodoPago:
        return {"ok": False, "estado": "sin_metodo_pago", "proveedor": "stripe"}
    except Exception as e:
        logger.error("_asegurar_cliente_y_metodo(%s): %s", id_empresa, e)
        return {"ok": False, "estado": "error", "error": str(e), "proveedor": "stripe"}

    try:
        kwargs = dict(
            amount=int(round(importe * 100)),
            currency="eur",
            customer=customer_id,
            payment_method=payment_method_id,
            payment_method_types=["sepa_debit"],
            off_session=True,
            confirm=True,
            description=referencia,
            metadata={"referencia": referencia or "", "id_empresa": id_empresa},
        )
        if es_nuevo:
            # Solo hace falta al crear el mandato la primera vez; los cargos posteriores reutilizan
            # el mandato ya asociado al PaymentMethod.
            kwargs["mandate_data"] = {"customer_acceptance": {"type": "offline"}}
        intent = stripe.PaymentIntent.create(**kwargs)
    except Exception as e:
        logger.error("PaymentIntent.create(%s): %s", id_empresa, e)
        return {"ok": False, "estado": "fallido", "error": str(e), "proveedor": "stripe"}

    estado_stripe = intent["status"]
    if estado_stripe == "succeeded":
        return {"ok": True, "estado": "pagado", "ref_externa": intent["id"], "proveedor": "stripe"}
    if estado_stripe == "processing":
        return {"ok": True, "estado": "procesando", "ref_externa": intent["id"], "proveedor": "stripe"}
    return {"ok": False, "estado": "fallido", "ref_externa": intent["id"], "proveedor": "stripe"}
