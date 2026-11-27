"""
Plan Freemium / de pago de los Portales Web (Portal B2B para empresas + Portal del Proveedor) —
petición explícita, 2026-11-27: ambos portales pasan a cobrar 0% de comisión (ver
`services.compras.comisiones_b2b.PCT_SIN_SUSCRIPCION`) y se convierten en un EMBUDO DE CAPTACIÓN
hacia el ERP, nunca un fin en sí mismos.

Una empresa/proveedor con suscripción ERP activa o en prueba tiene acceso COMPLETO a los
portales sin coste ni límites (reutiliza `comisiones_b2b.tiene_suscripcion_desktop_activa`/
`tiene_suscripcion_proveedor_activa` — misma resolución ya usada para la exención de comisión,
local o vía email). Para quien NO la tiene, hay 2 niveles:
  - **Freemium**: límites de uso claros (ver `LIMITES_FREEMIUM`).
  - **Plan de Pago del Portal** (mensual/anual): un escalón económico por debajo del ERP (Basic,
    29€/mes), con el MISMO criterio de descuento anual (16,7%, "2 meses gratis") y financiación a
    4 cuotas sin interés que ya usa `services.saas.planes`/`alta_comercial.confirmar_financiacion`.

Tabla propia `portal_suscripciones` (migración 0364) — PARALELA a `suscripciones`/`planes_saas`
(que son 1:1 con `empresas.id_empresa`, el ERP) porque un `suministrador` no tiene `id_empresa`
propio: forzarlo ahí mezclaría dos conceptos con PK distinta. El cobro real reutiliza Stripe:
pago íntegro (mensual/anual) con `price_data` INLINE en una Checkout Session normal
(`crear_checkout_session`/`confirmar_checkout`), y financiación a 4 cuotas del anual con el MISMO
patrón de 2 pasos que ya usa `alta_comercial.confirmar_financiacion` para el ERP — Setup Session
para vincular el método de pago, luego un `SubscriptionSchedule` de 2 fases
(`crear_checkout_session_financiada`/`confirmar_checkout_financiado`), con los `stripe.Price`
creados AL VUELO (nunca un Price ID fijo de variable de entorno, a diferencia del ERP: el precio
del portal es dinámico/calculado, no de catálogo) — ninguna de las dos rutas depende de crear
nada de antemano en el dashboard de Stripe. `confirmar_checkout_generico` resuelve sola cuál de
las dos aplica, para que la ruta `/plan/exito` de cada portal sea una sola.

Coste de infraestructura: NO hay factura real en este repositorio (confirmado explícito,
`INVENTARIO_INFRAESTRUCTURA_PRODUCCION.md`: "no hay infraestructura de producción en este
entorno"). `COSTE_SERVIDOR_MENSUAL_EUR` es una ESTIMACIÓN pública razonable (Hetzner Cloud, el
VPS único de 4GB que ya describe `docker-compose.prod.yml`), documentada y declarada aquí mismo
como punto ÚNICO de ajuste — corrígela en cuanto tengas la factura real; el resto de la fórmula
(amortización entre tenants + margen + tope) no cambia.
"""

import datetime
import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("portal_plan")

# ── Coste de infraestructura (ESTIMADO — editar aquí con la factura real) ────────────────────
COSTE_SERVIDOR_MENSUAL_EUR = 10.0   # Hetzner Cloud, VPS único 4GB compartido por TODOS los tenants
COSTE_SOPORTE_MENSUAL_EUR = 0.0     # sin coste de soporte dedicado documentado todavía
TENANTS_AMORTIZACION = 50           # nº de cuentas de pago del portal entre las que se reparte el coste fijo
MARGEN_PCT = 100.0                  # margen sobre el coste puro (100% = precio final = 2x coste)
PRECIO_MAXIMO_EUR = 15.0            # tope duro: siempre un escalón por debajo del Basic ERP (29€/mes)
PRECIO_MINIMO_EUR = 5.0             # piso: nunca un precio ridículo que no cubra nada

# ── Mismo criterio que `services.saas.planes` para el ERP ────────────────────────────────────
DESCUENTO_ANUAL_PCT = 16.7          # "2 meses gratis" — idéntico al ERP
NUM_CUOTAS_ANUAL = 4                # financiación sin interés, mismo patrón que alta_comercial.py

CODIGO_PLAN_PORTAL = "PORTAL"
NOMBRE_PLAN_PORTAL = "Smart Manager Portal"

TIPOS_SUJETO = ("empresa", "proveedor")
CICLOS = ("mensual", "anual")
ESTADOS = ("activa", "cancelada", "impagada")


def precio_mensual_portal() -> float:
    """Precio base mensual del Plan de Pago del Portal — fórmula documentada y configurable (ver
    constantes arriba): coste de infraestructura amortizado entre tenants + margen, acotado entre
    `PRECIO_MINIMO_EUR` y `PRECIO_MAXIMO_EUR` (siempre por debajo del Basic ERP)."""
    coste_total = COSTE_SERVIDOR_MENSUAL_EUR + COSTE_SOPORTE_MENSUAL_EUR
    coste_por_tenant = coste_total / max(1, TENANTS_AMORTIZACION)
    precio = coste_por_tenant * (1 + MARGEN_PCT / 100.0)
    return round(min(max(precio, PRECIO_MINIMO_EUR), PRECIO_MAXIMO_EUR), 2)


def precio_anual_portal() -> float:
    """Precio anual = 12 meses con el 16,7% de descuento — mismo criterio exacto que
    `services.saas.planes.PLANES` para los 3 planes del ERP (comentario de ese módulo: "2 meses
    gratis frente al mensual, ~16,7% de descuento")."""
    return round(precio_mensual_portal() * 12 * (1 - DESCUENTO_ANUAL_PCT / 100.0), 2)


def cuota_4_pagos() -> float:
    """Importe de cada una de las 4 cuotas trimestrales SIN interés del plan anual — mismo
    criterio exacto que `alta_comercial.confirmar_financiacion`/`sitio_oficial.py` para el ERP
    (cuota = precio_anual / 4, sin recargo por financiar)."""
    return round(precio_anual_portal() / NUM_CUOTAS_ANUAL, 2)


# ── Límites Freemium (sin ERP, sin Plan de Pago del Portal) ──────────────────────────────────
# None = sin límite. "usuarios" es metadato informativo: HOY cada empresa/proveedor tiene un
# único login compartido en ambos portales (confirmado, sin concepto de multiusuario todavía) —
# se deja declarado para cuando exista gestión de usuarios del portal, no se "aplica" activamente
# porque no hay nada que contar todavía (freemium=1 ya es la realidad actual de por sí).
LIMITES_FREEMIUM = {
    "b2b": {"pedidos_mes": 10, "proveedores_activos": 3, "usuarios": 1},
    "proveedor": {"catalogo_items": 25, "usuarios": 1},
}
LIMITES_PAGO = {
    "b2b": {"pedidos_mes": None, "proveedores_activos": None, "usuarios": 5},
    "proveedor": {"catalogo_items": None, "usuarios": 5},
}

# Umbral de aviso preventivo (petición explícita: "aviso antes de llegar al tope", "sin bloquear
# abruptamente") — al 80% del límite se muestra el banner de aviso; al 100% se bloquea la acción.
UMBRAL_AVISO_PCT = 0.8


def _emp_o_prov_tiene_erp(tipo_sujeto: str, id_sujeto) -> bool:
    """¿Esta empresa/proveedor tiene acceso COMPLETO porque tiene (ella misma) una suscripción
    activa o en prueba al ERP? Reutiliza EXACTAMENTE la misma resolución que ya usa
    `comisiones_b2b` para la exención de comisión (local o vía email) — cero lógica duplicada."""
    from src.services.compras import comisiones_b2b as CB
    if tipo_sujeto == "empresa":
        return CB.tiene_suscripcion_desktop_activa(id_sujeto)
    return CB.tiene_suscripcion_desktop_activa_proveedor(id_sujeto)


def obtener_portal_suscripcion(tipo_sujeto: str, id_sujeto) -> dict | None:
    """Fila ACTIVA de `portal_suscripciones` para este sujeto, o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM portal_suscripciones WHERE tipo_sujeto=%s AND id_sujeto=%s AND "
                "estado='activa' ORDER BY id DESC LIMIT 1", (tipo_sujeto, str(id_sujeto)))
            r = cur.fetchone()
            if not r:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, r)) if not isinstance(r, dict) else r
    except Exception as e:
        logger.error("obtener_portal_suscripcion(%s,%s): %s", tipo_sujeto, id_sujeto, e)
        return None


def tier_efectivo(tipo_sujeto: str, id_sujeto) -> str:
    """'erp' | 'pago' | 'freemium' — nivel real de acceso de esta empresa/proveedor en el portal."""
    if _emp_o_prov_tiene_erp(tipo_sujeto, id_sujeto):
        return "erp"
    if obtener_portal_suscripcion(tipo_sujeto, id_sujeto):
        return "pago"
    return "freemium"


# ── Contadores de uso (sobre tablas YA existentes — sin tabla de log nueva) ──────────────────
def _contar(sql, params) -> int:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception as e:
        logger.error("portal_plan._contar(%s): %s", sql, e)
        return 0


def _contar_pedidos_mes_b2b(id_empresa) -> int:
    inicio_mes = datetime.date.today().replace(day=1)
    return _contar(
        "SELECT COUNT(*) FROM transaccion_comercial WHERE id_empresa=%s AND origen='b2b' "
        "AND DATE(creada) >= %s", (id_empresa, inicio_mes))


def _contar_proveedores_activos(id_empresa) -> int:
    return _contar(
        "SELECT COUNT(*) FROM proveedores WHERE id_empresa=%s AND homologado=1", (id_empresa,))


def _contar_catalogo_items(id_suministrador) -> int:
    return _contar(
        "SELECT COUNT(*) FROM b2b_catalogo WHERE id_suministrador=%s AND activo=1",
        (id_suministrador,))


_CONTADORES = {
    ("b2b", "pedidos_mes"): _contar_pedidos_mes_b2b,
    ("b2b", "proveedores_activos"): _contar_proveedores_activos,
    ("proveedor", "catalogo_items"): _contar_catalogo_items,
}


def limite(portal: str, recurso: str, tipo_sujeto: str, id_sujeto) -> dict:
    """{limite, usado, disponible, ok, aviso, tier} — mismo patrón que
    `services.saas.licensing.limite_disponible`. `portal`: 'b2b'|'proveedor'. Con ERP o Plan de
    Pago del Portal → sin límite. `aviso=True` al superar `UMBRAL_AVISO_PCT` del límite (para el
    banner preventivo, sin bloquear todavía)."""
    tier = tier_efectivo(tipo_sujeto, id_sujeto)
    if tier in ("erp", "pago"):
        return {"limite": None, "usado": 0, "disponible": None, "ok": True, "aviso": False,
                "tier": tier}
    lim = (LIMITES_FREEMIUM.get(portal) or {}).get(recurso)
    fn = _CONTADORES.get((portal, recurso))
    usado = fn(id_sujeto) if fn else 0
    if lim is None:
        return {"limite": None, "usado": usado, "disponible": None, "ok": True, "aviso": False,
                "tier": tier}
    return {"limite": lim, "usado": usado, "disponible": max(0, lim - usado),
           "ok": usado < lim, "aviso": usado >= lim * UMBRAL_AVISO_PCT, "tier": tier}


def crear_checkout_session(tipo_sujeto: str, id_sujeto, *, ciclo: str, email: str,
                          success_url: str, cancel_url: str) -> dict:
    """Crea una sesión de Stripe Checkout para el Plan de Pago del Portal — `price_data` INLINE
    (sin ningún Price pre-creado en el dashboard de Stripe: se genera al vuelo con el precio YA
    calculado por `precio_mensual_portal`/`precio_anual_portal`), mismo SDK que ya usa
    `sitio_oficial.py` para el ERP. `ciclo`: 'mensual'|'anual' (pago íntegro — para financiar el
    anual en 4 cuotas, ver `crear_checkout_session_financiada` en su lugar). Devuelve {ok, url} o
    {ok: False, error}."""
    import os
    secreto = os.environ.get("STRIPE_SECRET_KEY")
    if not secreto:
        return {"ok": False, "error": "El pago no está disponible ahora mismo (Stripe no configurado)."}
    if ciclo not in CICLOS:
        return {"ok": False, "error": "Ciclo de facturación no válido."}
    try:
        import stripe
        stripe.api_key = secreto
        if ciclo == "mensual":
            unit_amount = int(round(precio_mensual_portal() * 100))
            recurring = {"interval": "month"}
        else:
            unit_amount = int(round(precio_anual_portal() * 100))
            recurring = {"interval": "year"}
        checkout = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "eur", "unit_amount": unit_amount, "recurring": recurring,
                    "product_data": {"name": f"{NOMBRE_PLAN_PORTAL} ({ciclo})"},
                },
                "quantity": 1,
            }],
            customer_email=email or None,
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"tipo": "portal_plan", "tipo_sujeto": tipo_sujeto,
                     "id_sujeto": str(id_sujeto), "ciclo": ciclo},
        )
        return {"ok": True, "url": checkout.url}
    except Exception as e:
        logger.error("crear_checkout_session(%s,%s,%s): %s", tipo_sujeto, id_sujeto, ciclo, e)
        return {"ok": False, "error": "No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."}


def crear_checkout_session_financiada(tipo_sujeto: str, id_sujeto, *, email: str,
                                      success_url: str, cancel_url: str) -> dict:
    """Primer paso de la financiación a 4 cuotas del plan ANUAL del portal (petición explícita,
    2026-11-27 — completa la pieza que había quedado pendiente de `crear_checkout_session`):
    Checkout en modo 'setup' que solo VINCULA un método de pago, sin cobrar nada todavía — mismo
    patrón de 2 pasos que `alta_comercial.confirmar_financiacion`/`sitio_oficial.py` usan para el
    ERP. El `SubscriptionSchedule` real (4 cuotas + luego anual indefinido) se crea en
    `confirmar_checkout_financiado`, una vez el método de pago queda vinculado."""
    import os
    secreto = os.environ.get("STRIPE_SECRET_KEY")
    if not secreto:
        return {"ok": False, "error": "El pago no está disponible ahora mismo (Stripe no configurado)."}
    try:
        import stripe
        stripe.api_key = secreto
        checkout = stripe.checkout.Session.create(
            mode="setup",
            customer_email=email or None,
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"tipo": "portal_plan_financiado", "tipo_sujeto": tipo_sujeto,
                     "id_sujeto": str(id_sujeto)},
        )
        return {"ok": True, "url": checkout.url}
    except Exception as e:
        logger.error("crear_checkout_session_financiada(%s,%s): %s", tipo_sujeto, id_sujeto, e)
        return {"ok": False, "error": "No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."}


def confirmar_checkout_financiado(session_id: str) -> dict:
    """Segundo paso: con el método de pago ya vinculado (Setup Session completada), crea el
    `SubscriptionSchedule` de 2 fases — EXACTO mismo patrón que
    `alta_comercial.confirmar_financiacion` para el ERP (fase 1 = 4 cuotas trimestrales de
    `cuota_4_pagos()`, vía un `stripe.Price` creado al vuelo; fase 2 = el precio anual normal,
    también creado al vuelo — a diferencia del ERP, el precio del portal es dinámico/calculado,
    así que aquí NUNCA se referencia un Price ID fijo de variable de entorno). Sin periodo de
    prueba (no se pidió para el plan del portal, a diferencia del ERP)."""
    import os
    secreto = os.environ.get("STRIPE_SECRET_KEY")
    if not secreto:
        return {"ok": False, "error": "Stripe no configurado."}
    try:
        import stripe
        stripe.api_key = secreto
        chk = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.error("confirmar_checkout_financiado retrieve(%s): %s", session_id, e)
        return {"ok": False, "error": "No se pudo verificar la vinculación del método de pago."}
    if chk.get("status") != "complete" or not chk.get("setup_intent"):
        return {"ok": False, "error": "La vinculación del método de pago no se completó."}
    meta = chk.get("metadata") or {}
    tipo_sujeto, id_sujeto = meta.get("tipo_sujeto"), meta.get("id_sujeto")
    if not (tipo_sujeto and id_sujeto):
        return {"ok": False, "error": "Sesión de pago inválida."}
    stripe_customer_id = chk.get("customer")
    try:
        setup_intent = stripe.SetupIntent.retrieve(chk["setup_intent"])
        metodo_pago = setup_intent.get("payment_method")
        if not metodo_pago:
            return {"ok": False, "error": "No se pudo vincular el método de pago."}
        stripe.PaymentMethod.attach(metodo_pago, customer=stripe_customer_id)
        stripe.Customer.modify(stripe_customer_id,
                               invoice_settings={"default_payment_method": metodo_pago})
        cuota = cuota_4_pagos()
        precio_anual = precio_anual_portal()
        precio_cuota = stripe.Price.create(
            currency="eur", unit_amount=int(round(cuota * 100)),
            recurring={"interval": "month", "interval_count": 3},
            product_data={"name": f"{NOMBRE_PLAN_PORTAL} (financiado, 4 cuotas trimestrales)"})
        precio_anual_obj = stripe.Price.create(
            currency="eur", unit_amount=int(round(precio_anual * 100)),
            recurring={"interval": "year"},
            product_data={"name": f"{NOMBRE_PLAN_PORTAL} (anual)"})
        schedule = stripe.SubscriptionSchedule.create(
            customer=stripe_customer_id, start_date="now", end_behavior="release",
            default_settings={"default_payment_method": metodo_pago},
            phases=[
                {"items": [{"price": precio_cuota["id"], "quantity": 1}], "iterations": 4},
                {"items": [{"price": precio_anual_obj["id"], "quantity": 1}]},
            ])
    except Exception as e:
        logger.error("confirmar_checkout_financiado SubscriptionSchedule(%s): %s", session_id, e)
        return {"ok": False, "error": "No se pudo programar las cuotas de financiación."}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE portal_suscripciones SET estado='cancelada', cancelada_en=NOW() WHERE "
                "tipo_sujeto=%s AND id_sujeto=%s AND estado='activa'", (tipo_sujeto, id_sujeto))
            cur.execute(
                "INSERT INTO portal_suscripciones (tipo_sujeto, id_sujeto, codigo_plan, ciclo, "
                "estado, financiado_4_cuotas, stripe_customer_id, stripe_subscription_id) "
                "VALUES (%s,%s,%s,'anual','activa',1,%s,%s)",
                (tipo_sujeto, id_sujeto, CODIGO_PLAN_PORTAL, stripe_customer_id,
                 schedule.get("subscription")))
            conn.commit()
        return {"ok": True, "tipo_sujeto": tipo_sujeto, "id_sujeto": id_sujeto, "ciclo": "anual"}
    except Exception as e:
        logger.error("confirmar_checkout_financiado persistir(%s): %s", session_id, e)
        return {"ok": False, "error": "El pago se programó pero no pudimos activar el plan. "
                                      "Escríbenos para resolverlo manualmente."}


def confirmar_checkout(session_id: str) -> dict:
    """Verifica una Checkout Session de Stripe ya completada y activa (o renueva)
    `portal_suscripciones` para el sujeto indicado en sus metadatos. Nunca activa nada sin
    confirmar el pago real contra Stripe (`payment_status`)."""
    import os
    secreto = os.environ.get("STRIPE_SECRET_KEY")
    if not secreto:
        return {"ok": False, "error": "Stripe no configurado."}
    try:
        import stripe
        stripe.api_key = secreto
        chk = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.error("confirmar_checkout retrieve(%s): %s", session_id, e)
        return {"ok": False, "error": "No se pudo verificar el pago."}
    if chk.get("payment_status") not in ("paid", "no_payment_required"):
        return {"ok": False, "error": "El pago no se ha completado todavía."}
    meta = chk.get("metadata") or {}
    tipo_sujeto, id_sujeto, ciclo = meta.get("tipo_sujeto"), meta.get("id_sujeto"), meta.get("ciclo")
    if not (tipo_sujeto and id_sujeto and ciclo):
        return {"ok": False, "error": "Sesión de pago inválida."}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE portal_suscripciones SET estado='cancelada', cancelada_en=NOW() WHERE "
                "tipo_sujeto=%s AND id_sujeto=%s AND estado='activa'", (tipo_sujeto, id_sujeto))
            cur.execute(
                "INSERT INTO portal_suscripciones (tipo_sujeto, id_sujeto, codigo_plan, ciclo, "
                "estado, stripe_customer_id, stripe_subscription_id) "
                "VALUES (%s,%s,%s,%s,'activa',%s,%s)",
                (tipo_sujeto, id_sujeto, CODIGO_PLAN_PORTAL, ciclo, chk.get("customer"),
                 chk.get("subscription")))
            conn.commit()
        return {"ok": True, "tipo_sujeto": tipo_sujeto, "id_sujeto": id_sujeto, "ciclo": ciclo}
    except Exception as e:
        logger.error("confirmar_checkout persistir(%s): %s", session_id, e)
        return {"ok": False, "error": "El pago se completó pero no pudimos activar el plan. "
                                      "Escríbenos para resolverlo manualmente."}


def resolver_sujeto_por_stripe_customer(customer_id) -> tuple:
    """(tipo_sujeto, id_sujeto) dueño de este Stripe customer en `portal_suscripciones`, o
    (None, None). Usado por el webhook de Stripe (`backend_central/rutas_stripe.py`) para saber
    si un evento de pago/cancelación es de un Plan de Pago del Portal — nunca de un plan ERP
    (tablas y resolución completamente distintas, ver `_resolver_empresa_y_config_por_customer`
    de ese mismo módulo)."""
    if not customer_id:
        return None, None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            # SIN filtrar por estado (a propósito): un evento puede llegar para revertir una
            # 'impagada' de vuelta a 'activa' (reintento de cobro con éxito) o para cancelar una
            # que ya estaba 'impagada' — en ambos casos tiene que seguir encontrando la MISMA fila
            # (la más reciente de este customer), nunca solo la que ya estuviera 'activa'.
            cur.execute(
                "SELECT tipo_sujeto, id_sujeto FROM portal_suscripciones WHERE "
                "stripe_customer_id=%s ORDER BY id DESC LIMIT 1", (customer_id,))
            r = cur.fetchone()
            if not r:
                return None, None
            return (r[0], r[1]) if not isinstance(r, dict) else (r["tipo_sujeto"], r["id_sujeto"])
    except Exception as e:
        logger.error("resolver_sujeto_por_stripe_customer(%s): %s", customer_id, e)
        return None, None


_EVENTOS_PAGADO = {"invoice.paid", "invoice.payment_succeeded"}
_EVENTOS_FALLIDO = {"invoice.payment_failed"}
_EVENTOS_CANCELADO = {"customer.subscription.deleted"}


def procesar_evento_webhook(tipo: str, customer_id: str) -> dict:
    """Pieza que completaba el flujo de pago del Plan de Pago del Portal (petición explícita,
    2026-11-27, cerrando el hueco ya señalado — "el webhook de renovación/cancelación queda
    pendiente"): traduce un evento de Stripe (pagado/fallido/cancelado) en el estado real de
    `portal_suscripciones` — equivalente ligero de `services.saas.billing.webhooks.
    procesar_evento` para el ERP, pero sobre `tipo_sujeto`+`id_sujeto` en vez de `id_empresa`
    (tablas y resolución independientes, nunca se mezclan). Llamado desde el MISMO endpoint de
    webhook que ya existía (`backend_central/rutas_stripe.py`) cuando el customer de Stripe no
    resuelve a ninguna empresa ERP — sin un segundo endpoint, sin un segundo secreto de Stripe."""
    tipo_sujeto, id_sujeto = resolver_sujeto_por_stripe_customer(customer_id)
    if not tipo_sujeto:
        return {"ok": False, "accion": "sin_sujeto"}
    if tipo in _EVENTOS_PAGADO:
        nuevo_estado = "activa"
    elif tipo in _EVENTOS_FALLIDO:
        nuevo_estado = "impagada"
    elif tipo in _EVENTOS_CANCELADO:
        nuevo_estado = "cancelada"
    else:
        return {"ok": False, "accion": "ignorado", "tipo": tipo}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            extra = ", cancelada_en=NOW()" if nuevo_estado == "cancelada" else ""
            # Misma fila EXACTA que acaba de resolver `resolver_sujeto_por_stripe_customer` (por
            # `stripe_customer_id`, la más reciente) — nunca "cualquier fila de este sujeto", que
            # podría alcanzar una suscripción antigua ya cancelada de verdad por otro motivo.
            cur.execute(
                f"UPDATE portal_suscripciones SET estado=%s{extra} WHERE stripe_customer_id=%s "
                "AND tipo_sujeto=%s AND id_sujeto=%s ORDER BY id DESC LIMIT 1",
                (nuevo_estado, customer_id, tipo_sujeto, id_sujeto))
            conn.commit()
        return {"ok": True, "accion": nuevo_estado, "tipo_sujeto": tipo_sujeto, "id_sujeto": id_sujeto}
    except Exception as e:
        logger.error("procesar_evento_webhook(%s,%s): %s", tipo, customer_id, e)
        return {"ok": False, "accion": "error"}


# ── PayPal como alternativa a Stripe (petición explícita, 2026-11-27) ─────────────────────────
# Suscripciones reales de PayPal (`/v1/billing/*`), EXACTO mismo patrón que `backend/
# sitio_oficial.py` usa para las suscripciones ERP — Smart Manager cobra DIRECTAMENTE en su propia
# cuenta (`PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` globales de siempre), nada de custodia ni
# reparto: esto NO es el PayPal marketplace de los portales (`tpv.pagos.paypal_connect`, pago
# directo al PROVEEDOR, credenciales propias de CADA proveedor — ver migr. 0366), es ingreso
# propio de Smart Manager, igual que el ERP.
#
# A diferencia de Stripe (que necesita el baile Checkout→Setup/SubscriptionSchedule porque el
# precio es dinámico), la Suscripción de PayPal ya define TODAS sus fases desde el principio —
# un único paso crea el Plan (al vuelo, con el precio YA calculado) + la Suscripción y redirige a
# aprobar. El contexto (tipo_sujeto/id_sujeto/ciclo/financiado) viaja en `custom_id` de la propia
# Suscripción — nunca en la sesión de Flask ni en la query string del retorno (que PayPal no
# garantiza): `confirmar_checkout_paypal` vuelve a consultar la Suscripción real y lee SU
# `custom_id`, mismo criterio "nunca confiar en la redirección por sí sola" que el resto de la app.
def _paypal_base() -> str:
    import os
    return ("https://api-m.sandbox.paypal.com" if os.environ.get("PAYPAL_MODO", "test") != "live"
           else "https://api-m.paypal.com")


def _paypal_token():
    import os
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
        logger.warning("_paypal_token (portal_plan) %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("_paypal_token (portal_plan): %s", e)
    return None


def _paypal_crear_plan_simple(token, *, ciclo: str, unit_amount: float) -> str | None:
    """Producto + Plan de PayPal AL VUELO con UN solo ciclo REGULAR (pago íntegro mensual/anual,
    sin prueba — el Plan de Pago del Portal no tiene periodo de prueba). Devuelve el `plan_id` o
    None si falla (degrada honestamente, nunca finge un plan)."""
    import requests
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    interval_unit = "MONTH" if ciclo == "mensual" else "YEAR"
    try:
        rp = requests.post(f"{_paypal_base()}/v1/catalogs/products", headers=headers, timeout=25,
                           json={"name": f"{NOMBRE_PLAN_PORTAL} ({ciclo})", "type": "SERVICE",
                                "category": "SOFTWARE"})
        if rp.status_code not in (200, 201):
            logger.warning("PayPal crear producto (portal_plan) %s: %s", rp.status_code, rp.text[:200])
            return None
        product_id = rp.json().get("id")
        r = requests.post(f"{_paypal_base()}/v1/billing/plans", headers=headers, timeout=25, json={
            "product_id": product_id, "name": f"{NOMBRE_PLAN_PORTAL} ({ciclo})",
            "billing_cycles": [{
                "tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
                "frequency": {"interval_unit": interval_unit, "interval_count": 1},
                "pricing_scheme": {"fixed_price": {"value": f"{unit_amount:.2f}", "currency_code": "EUR"}},
            }],
            "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 3},
        })
        if r.status_code not in (200, 201):
            logger.warning("PayPal crear plan (portal_plan) %s: %s", r.status_code, r.text[:200])
            return None
        return r.json().get("id")
    except Exception as e:
        logger.error("_paypal_crear_plan_simple: %s", e)
        return None


def _paypal_crear_plan_financiado(token, *, cuota: float) -> str | None:
    """Hallazgo real (2026-11-27, probado contra la API real de PayPal antes de desplegar): el
    patrón de `sitio_oficial._paypal_crear_plan_financiacion` para el ERP (2 `billing_cycles`
    REGULAR — 4 cuotas, luego el anual para siempre) NO es válido en PayPal — la API lo rechaza con
    422 `MULTIPLE_REGULAR_BILLING_CYCLE_NOT_SUPPORTED` ("Only one regular billing cycle is
    allowed"). Esto afecta también al ERP (nunca se había probado en vivo) — pendiente de
    corregir allí igual que aquí.

    Por eso el Plan de PayPal financiado usa un ÚNICO ciclo REGULAR: `cuota` cada 3 meses, PARA
    SIEMPRE (`total_cycles=0`) — en vez de "4 cuotas y luego cambia a anual" (como sí puede hacer
    Stripe con un `SubscriptionSchedule` de 2 fases, que no tiene esta limitación). El coste total
    por año es idéntico (`cuota*4 = precio_anual`): la diferencia real es que, pagando por PayPal,
    la financiación trimestral continúa cada año en vez de volver a un único pago anual a partir
    del segundo año."""
    import requests
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        rp = requests.post(f"{_paypal_base()}/v1/catalogs/products", headers=headers, timeout=25,
                           json={"name": f"{NOMBRE_PLAN_PORTAL} (financiado)", "type": "SERVICE",
                                "category": "SOFTWARE"})
        if rp.status_code not in (200, 201):
            logger.warning("PayPal crear producto (financiación portal) %s: %s",
                          rp.status_code, rp.text[:200])
            return None
        product_id = rp.json().get("id")
        billing_cycles = [
            {"tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
             "frequency": {"interval_unit": "MONTH", "interval_count": 3},
             "pricing_scheme": {"fixed_price": {"value": f"{cuota:.2f}", "currency_code": "EUR"}}},
        ]
        r = requests.post(f"{_paypal_base()}/v1/billing/plans", headers=headers, timeout=25, json={
            "product_id": product_id, "name": f"{NOMBRE_PLAN_PORTAL} — financiado en 4 cuotas",
            "billing_cycles": billing_cycles,
            "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 3},
        })
        if r.status_code not in (200, 201):
            logger.warning("PayPal crear plan (financiación portal) %s: %s", r.status_code, r.text[:200])
            return None
        return r.json().get("id")
    except Exception as e:
        logger.error("_paypal_crear_plan_financiado: %s", e)
        return None


def _paypal_crear_suscripcion(token, *, plan_id, email, custom_id, return_url, cancel_url) -> dict:
    import requests
    try:
        r = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=25,
            json={
                "plan_id": plan_id, "custom_id": custom_id,
                "subscriber": {"email_address": email} if email else {},
                "application_context": {
                    "brand_name": "Smart Manager", "locale": "es-ES",
                    "shipping_preference": "NO_SHIPPING", "user_action": "SUBSCRIBE_NOW",
                    "return_url": return_url, "cancel_url": cancel_url,
                },
            })
        if r.status_code not in (200, 201):
            logger.warning("PayPal crear suscripción (portal_plan) %s: %s", r.status_code, r.text[:200])
            return {"ok": False}
        j = r.json()
        approve_url = next((l.get("href") for l in j.get("links", []) if l.get("rel") == "approve"), None)
        if not approve_url:
            return {"ok": False}
        return {"ok": True, "subscription_id": j.get("id"), "approve_url": approve_url}
    except Exception as e:
        logger.error("_paypal_crear_suscripcion (portal_plan): %s", e)
        return {"ok": False}


def _paypal_obtener_suscripcion(token, subscription_id):
    import requests
    try:
        r = requests.get(f"{_paypal_base()}/v1/billing/subscriptions/{subscription_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=25)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error("_paypal_obtener_suscripcion (portal_plan): %s", e)
    return None


def crear_checkout_session_paypal(tipo_sujeto: str, id_sujeto, *, ciclo: str, email: str,
                                  success_url: str, cancel_url: str) -> dict:
    """Equivalente PayPal de `crear_checkout_session` — pago íntegro mensual/anual. Devuelve
    {ok, url} o {ok: False, error}."""
    import json as _json
    if ciclo not in CICLOS:
        return {"ok": False, "error": "Ciclo de facturación no válido."}
    token = _paypal_token()
    if not token:
        return {"ok": False, "error": "El pago no está disponible ahora mismo (PayPal no configurado)."}
    unit_amount = precio_mensual_portal() if ciclo == "mensual" else precio_anual_portal()
    plan_id = _paypal_crear_plan_simple(token, ciclo=ciclo, unit_amount=unit_amount)
    if not plan_id:
        return {"ok": False, "error": "No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."}
    custom_id = _json.dumps({"s": tipo_sujeto, "i": str(id_sujeto), "c": ciclo, "f": False})
    r = _paypal_crear_suscripcion(token, plan_id=plan_id, email=email, custom_id=custom_id,
                                  return_url=success_url, cancel_url=cancel_url)
    if not r.get("ok"):
        return {"ok": False, "error": "No se pudo iniciar el pago con PayPal. Inténtalo de nuevo en unos minutos."}
    return {"ok": True, "url": r["approve_url"]}


def crear_checkout_session_financiada_paypal(tipo_sujeto: str, id_sujeto, *, email: str,
                                             success_url: str, cancel_url: str) -> dict:
    """Equivalente PayPal de `crear_checkout_session_financiada` — a diferencia de Stripe, aquí NO
    hace falta un segundo paso: el Plan se crea de una vez y la Suscripción ya lo incluye desde el
    principio. Ver el docstring de `_paypal_crear_plan_financiado` para el porqué NO es un plan de
    2 fases (4 cuotas → anual) como en Stripe: PayPal factura la cuota trimestral para siempre, en
    vez de pasar a un único cobro anual a partir del segundo año — mismo coste total por año."""
    import json as _json
    token = _paypal_token()
    if not token:
        return {"ok": False, "error": "El pago no está disponible ahora mismo (PayPal no configurado)."}
    plan_id = _paypal_crear_plan_financiado(token, cuota=cuota_4_pagos())
    if not plan_id:
        return {"ok": False, "error": "No se pudo iniciar el pago. Inténtalo de nuevo en unos minutos."}
    custom_id = _json.dumps({"s": tipo_sujeto, "i": str(id_sujeto), "c": "anual", "f": True})
    r = _paypal_crear_suscripcion(token, plan_id=plan_id, email=email, custom_id=custom_id,
                                  return_url=success_url, cancel_url=cancel_url)
    if not r.get("ok"):
        return {"ok": False, "error": "No se pudo iniciar el pago con PayPal. Inténtalo de nuevo en unos minutos."}
    return {"ok": True, "url": r["approve_url"]}


def confirmar_checkout_paypal(subscription_id: str) -> dict:
    """Confirma una Suscripción de PayPal del Plan de Pago del Portal — NUNCA se confía en la
    redirección por sí sola: se vuelve a consultar la Suscripción real (y se activa explícitamente
    si quedó en APPROVED, mismo criterio que `sitio_oficial.checkout_paypal_exito`) antes de
    activar nada. El contexto viaja en el propio `custom_id` de la Suscripción, fijado al crearla
    — nunca en la sesión de Flask."""
    import json as _json
    if not subscription_id:
        return {"ok": False, "error": "Falta el identificador de la suscripción."}
    token = _paypal_token()
    if not token:
        return {"ok": False, "error": "PayPal no configurado."}
    sus = _paypal_obtener_suscripcion(token, subscription_id)
    if not sus:
        return {"ok": False, "error": "No se pudo verificar el pago."}
    estado = sus.get("status")
    if estado == "APPROVED":
        import requests
        try:
            requests.post(
                f"{_paypal_base()}/v1/billing/subscriptions/{subscription_id}/activate",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=25, json={"reason": "Alta del Plan de Pago del Portal"})
            sus = _paypal_obtener_suscripcion(token, subscription_id) or sus
            estado = sus.get("status")
        except Exception as e:
            logger.error("confirmar_checkout_paypal activar(%s): %s", subscription_id, e)
    if estado != "ACTIVE":
        return {"ok": False, "error": "El pago no se ha completado todavía."}
    try:
        ctx = _json.loads(sus.get("custom_id") or "{}")
        tipo_sujeto, id_sujeto, ciclo, financiado = ctx["s"], ctx["i"], ctx["c"], bool(ctx.get("f"))
    except Exception as e:
        logger.error("confirmar_checkout_paypal custom_id(%s): %s", subscription_id, e)
        return {"ok": False, "error": "Sesión de pago inválida."}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE portal_suscripciones SET estado='cancelada', cancelada_en=NOW() WHERE "
                "tipo_sujeto=%s AND id_sujeto=%s AND estado='activa'", (tipo_sujeto, id_sujeto))
            cur.execute(
                "INSERT INTO portal_suscripciones (tipo_sujeto, id_sujeto, codigo_plan, ciclo, "
                "estado, financiado_4_cuotas, paypal_subscription_id) "
                "VALUES (%s,%s,%s,%s,'activa',%s,%s)",
                (tipo_sujeto, id_sujeto, CODIGO_PLAN_PORTAL, ciclo, int(financiado), subscription_id))
            conn.commit()
        return {"ok": True, "tipo_sujeto": tipo_sujeto, "id_sujeto": id_sujeto, "ciclo": ciclo}
    except Exception as e:
        logger.error("confirmar_checkout_paypal persistir(%s): %s", subscription_id, e)
        return {"ok": False, "error": "El pago se completó pero no pudimos activar el plan. "
                                      "Escríbenos para resolverlo manualmente."}


def resolver_sujeto_por_paypal_subscription(subscription_id) -> tuple:
    """(tipo_sujeto, id_sujeto) dueño de esta Suscripción de PayPal en `portal_suscripciones`, o
    (None, None) — equivalente PayPal de `resolver_sujeto_por_stripe_customer`. Preparado para
    cuando exista un receptor de webhooks de PayPal (hueco ya documentado, ver memoria del
    proyecto: hoy ningún flujo de PayPal de la app tiene webhook, ERP incluido)."""
    if not subscription_id:
        return None, None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tipo_sujeto, id_sujeto FROM portal_suscripciones WHERE "
                "paypal_subscription_id=%s ORDER BY id DESC LIMIT 1", (subscription_id,))
            r = cur.fetchone()
            if not r:
                return None, None
            return (r[0], r[1]) if not isinstance(r, dict) else (r["tipo_sujeto"], r["id_sujeto"])
    except Exception as e:
        logger.error("resolver_sujeto_por_paypal_subscription(%s): %s", subscription_id, e)
        return None, None


def confirmar_checkout_generico(session_id: str) -> dict:
    """Punto único de confirmación para la ruta `/plan/exito` de ambos portales: resuelve sola si
    la sesión fue un cobro directo (mensual/anual íntegro, `mode='subscription'`) o el primer
    paso de la financiación a 4 cuotas (`mode='setup'`), sin que la ruta Flask tenga que saberlo."""
    import os
    secreto = os.environ.get("STRIPE_SECRET_KEY")
    if not secreto:
        return {"ok": False, "error": "Stripe no configurado."}
    try:
        import stripe
        stripe.api_key = secreto
        chk = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.error("confirmar_checkout_generico retrieve(%s): %s", session_id, e)
        return {"ok": False, "error": "No se pudo verificar el pago."}
    if chk.get("mode") == "setup":
        return confirmar_checkout_financiado(session_id)
    return confirmar_checkout(session_id)


__all__ = [
    "CODIGO_PLAN_PORTAL", "NOMBRE_PLAN_PORTAL", "TIPOS_SUJETO", "CICLOS", "ESTADOS",
    "LIMITES_FREEMIUM", "LIMITES_PAGO", "UMBRAL_AVISO_PCT",
    "precio_mensual_portal", "precio_anual_portal", "cuota_4_pagos",
    "obtener_portal_suscripcion", "tier_efectivo", "limite",
    "crear_checkout_session", "confirmar_checkout",
    "crear_checkout_session_financiada", "confirmar_checkout_financiado",
    "confirmar_checkout_generico",
    "crear_checkout_session_paypal", "crear_checkout_session_financiada_paypal",
    "confirmar_checkout_paypal", "resolver_sujeto_por_paypal_subscription",
]
