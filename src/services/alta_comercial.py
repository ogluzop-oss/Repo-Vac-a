"""
Alta comercial de clientes nuevos desde el sitio oficial (`src.backend.sitio_oficial`,
smartmanager-app.com) — registro, pago y aprovisionamiento del primer ordenador.

IMPORTANTE (corrige un error de diseño del primer intento, 2026-11-13): el alta NO crea nada en el
servidor CENTRAL de licencias (`src.backend_central`, pensado para instalaciones on-prem
independientes, cada una con su PROPIA base de datos — ver su docstring). Este despliegue es un
SaaS multiempresa de verdad: cada empresa nueva recibe su PROPIA base de datos MariaDB, aislada a
nivel de motor (2026-11-14, cierre de brecha de seguridad — ver `services.provisioning.
aprovisionar_tenant_nuevo`), en vez de una fila más en una base compartida. Solo los METADATOS de
la cuenta web/licencia (que SÍ necesitan resolverse ANTES de saber a qué empresa pertenecen, o que
sirven para encontrar a qué base física conectarse) viven en la base compartida de siempre:
`tenants_db` (mapeo `id_empresa -> base física`), `codigos_aprovisionamiento`,
`cuentas_web_central`, `altas_web_stripe`, `instalaciones_db`. Reutiliza:

- `services.provisioning.aprovisionar_tenant_nuevo` — crea la base física nueva + empresa + centro
  principal, YA con el esquema completo aplicado.
- `services.provisioning.config_tenant(id_empresa)` — resuelve la base física de una empresa YA
  existente (o `None` para las 3 empresas de ANTES de este cambio, que siguen en la compartida).
- `services.saas.suscripciones` / `licensing` — activación del plan contratado (sobre la base del
  tenant).
- `services.provisioning.generar_codigo` — el MISMO código que ya genera el botón 🔑 de
  "Configuración → Datos de empresa → Centros" para emparejar un ordenador nuevo (consumido por
  `POST /provisioning/emparejar`, YA canjeable desde la pantalla de primer arranque de la app de
  escritorio, `main.py::_pantalla_primer_arranque` — esa pantalla ya existía completa, no hacía
  falta construir nada nuevo ahí). Con una caducidad más larga que el uso interno (30 min no basta
  para "pago hoy, instalo la app cuando pueda" — ver `MINUTOS_CADUCIDAD_WEB`).

`backend_central.rutas_sitio_web` (el primer intento) queda `@deprecated`: el código sigue ahí
(Strangler) pero el sitio oficial ya no lo usa.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("services.alta_comercial")

MINUTOS_CADUCIDAD_WEB = 60 * 24 * 7  # 7 días: tiempo realista entre pagar y abrir el instalador.


def _fila(cur, r):
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _cuenta_por_email(cur, email):
    cur.execute("SELECT id, email, password_hash, id_empresa_central FROM cuentas_web_central "
               "WHERE email=%s", (email,))
    return _fila(cur, cur.fetchone())


def preregistrar(email) -> dict:
    """Valida que el email no tenga ya cuenta, SIN crear nada todavía (paso previo a mandar al
    cliente a Stripe Checkout — evita checkouts abandonados que dejarían una empresa huérfana)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        if _cuenta_por_email(cur, email):
            return {"ok": False, "error": "Ya existe una cuenta con ese email."}
    return {"ok": True}


def _activar_plan_pagado(id_empresa, plan, *, precio, referencia, config=None, ciclo="mensual",
                         proximo_cobro=None):
    """Activa la suscripción SIN pasar por el cobro recurrente interno (SEPA, pensado para
    RENOVACIONES futuras): el primer mes/año ya se cobró de verdad en Stripe Checkout, así que
    aquí solo se registra esa factura/pago REAL y se activa el plan — mismo criterio ya usado y
    verificado en el primer intento (evita el intento de cobro redundante/erróneo vía SEPA).

    `config` opcional: base física del tenant (ver `services.provisioning.config_tenant`) — la
    suscripción/factura/pago se guardan AHÍ, no en la base compartida.

    `precio` puede ser 0 (petición explícita, 2026-11-22 — periodo de prueba de 7 días): cuando
    Stripe confirma `payment_status=no_payment_required` no se ha cobrado nada todavía, así que se
    registra la factura/pago de la primera llamada por 0€ — nunca se finge un cobro de tarifa
    completa que no ha ocurrido. El cobro REAL (prorrateado) lo hará Stripe automáticamente al
    terminar la prueba; esta función no lo registra (llega vía webhook, fuera de este alcance).

    `proximo_cobro` opcional (idem, 2026-11-22): si se pasa, sustituye el cálculo local
    aproximado por la fecha REAL que ya conoce quien llama (resuelta contra la propia suscripción
    de Stripe) — usado para la prueba gratuita, donde el próximo cobro no cae a `ciclo` días vista
    sino al terminar los 7 días de prueba.

    Bug real corregido (2026-11-15, al añadir el ciclo anual): `S.crear(..., prueba=True)` calcula
    `proximo_cobro` con `dias_prueba` (30 días), NO con la duración real del `ciclo` — pasaba
    desapercibido porque hasta ahora el único ciclo de pago web era "mensual" (30 días, coincidía
    por casualidad). Con "anual" ya no coincide, así que aquí se recalcula `proximo_cobro` con la
    duración real del ciclo al activar (salvo que ya se pase uno explícito, ver arriba)."""
    import datetime as _dt

    from src.services.saas import licensing as _L
    from src.services.saas import suscripciones as S

    sid = S.crear(id_empresa, plan, ciclo=ciclo, prueba=True, dias_prueba=30, config=config)
    if not sid:
        return False
    if proximo_cobro is None:
        proximo_cobro = _dt.date.today() + _dt.timedelta(days=S.CICLOS.get(ciclo, 30))
    estado_factura = "pagada" if precio else "pendiente"
    estado_pago = "pagado" if precio else "pendiente"
    with obtener_conexion(config) as conn, conn.cursor() as cur:
        cur.execute("UPDATE suscripciones SET estado='activa', proximo_cobro=%s WHERE id=%s",
                   (proximo_cobro, sid))
        cur.execute(
            "INSERT INTO facturas_saas (id_empresa, id_suscripcion, numero, importe, estado, "
            "fecha, concepto) VALUES (%s,%s,%s,%s,%s,%s,'suscripcion')",
            (id_empresa, sid, referencia, precio, estado_factura, _dt.date.today()))
        fid = cur.lastrowid
        cur.execute(
            "INSERT INTO pagos_saas (id_empresa, id_factura, proveedor, importe, estado, "
            "ref_externa, intentos) VALUES (%s,%s,'stripe_checkout',%s,%s,%s,1)",
            (id_empresa, fid, precio, estado_pago, referencia))
        conn.commit()
    _L.asignar_plan(id_empresa, plan, estado="activa", config=config)
    return True


def _generar_codigo_provisioning(id_centro, id_empresa):
    from src.services import provisioning
    r = provisioning.generar_codigo(id_centro, id_empresa, minutos=MINUTOS_CADUCIDAD_WEB)
    return r.get("codigo") if r.get("ok") else None


def registrar_gratis(nombre_empresa, email, password_hash, *, ciclo="mensual") -> dict:
    """Alta directa sin pago, para cuando el plan contratado tenga precio 0 (hoy ningún plan lo
    tiene — Básico pasó a 29€/mes — se conserva lista por si vuelve a haber uno)."""
    from src.services import provisioning

    tenant = provisioning.aprovisionar_tenant_nuevo(nombre_empresa, email)
    if not tenant.get("ok"):
        return {"ok": False, "error": "No se pudo registrar la empresa."}
    id_empresa, id_centro = tenant["id_empresa"], tenant["id_centro"]
    cfg_tenant = provisioning.config_tenant(id_empresa)

    from src.services.saas import suscripciones as S
    S.crear(id_empresa, "BASIC", ciclo=ciclo, prueba=False, config=cfg_tenant)

    codigo = _generar_codigo_provisioning(id_centro, id_empresa)
    if not codigo:
        return {"ok": False, "error": "No se pudo generar el código de instalación."}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO cuentas_web_central (email, password_hash, id_empresa_central) "
                   "VALUES (%s,%s,%s)", (email, password_hash, id_empresa))
        conn.commit()

    logger.info("Alta gratuita vía sitio oficial: empresa=%s email=%s", id_empresa, email)
    return {"ok": True, "codigo": codigo, "plan": "BASIC", "id_empresa": id_empresa}


def _paypal_token_directo():
    """Token OAuth2 de la cuenta de PayPal de Smart Manager, PLANA (no marketplace) — las mismas
    `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` que usa `sitio_oficial` para crear la suscripción."""
    import os

    import requests
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    base = ("https://api-m.sandbox.paypal.com" if os.environ.get("PAYPAL_MODO", "test") != "live"
           else "https://api-m.paypal.com")
    try:
        r = requests.post(f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                          auth=(client_id, client_secret), timeout=20)
        if r.status_code == 200:
            return base, r.json().get("access_token")
    except Exception as e:
        logger.warning("_paypal_token_directo: %s", e)
    return base, None


def _resolver_prueba_paypal(paypal_subscription_id):
    """Equivalente de la rama `stripe_subscription_id` de abajo, para PayPal: ¿sigue en el ciclo de
    prueba de 7 días? Devuelve (precio_cero: bool, proximo_cobro: date|None) — nunca lanza, nunca
    finge: ante cualquier fallo, deja el precio de catálogo tal cual (como si no hubiera prueba
    detectada) en vez de adivinar."""
    import requests
    base, token = _paypal_token_directo()
    if not token:
        return False, None
    try:
        r = requests.get(f"{base}/v1/billing/subscriptions/{paypal_subscription_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.status_code != 200:
            return False, None
        j = r.json()
        info = j.get("billing_info") or {}
        ciclos = info.get("cycle_executions") or []
        en_prueba = any(c.get("tenure_type") == "TRIAL" and int(c.get("cycles_completed") or 0) == 0
                       for c in ciclos)
        proximo_cobro = None
        siguiente = info.get("next_billing_time")
        if siguiente:
            import datetime as _dt
            proximo_cobro = _dt.datetime.fromisoformat(
                siguiente.replace("Z", "+00:00")).date()
        return en_prueba, proximo_cobro
    except Exception as e:
        logger.warning("_resolver_prueba_paypal(%s): %s", paypal_subscription_id, e)
        return False, None


def confirmar_pago(*, session_id, plan, email, nombre_empresa, password_hash, stripe_customer_id=None,
                   ciclo="mensual", stripe_subscription_id=None, paypal_subscription_id=None) -> dict:
    """Tras un Stripe Checkout con `payment_status` en `paid` o `no_payment_required`, O tras una
    Suscripción de PayPal activa (petición explícita, 2026-11-23: PayPal como alternativa en la web
    oficial) — verificado por quien llama ANTES de invocar esto, esta función no vuelve a
    comprobarlo. Idempotente por `session_id` (para PayPal, `f"paypal_{subscription_id}"" — ver
    `sitio_oficial.checkout_paypal_exito`): si ya se generó un alta para esa sesión, devuelve el
    código ya existente en vez de duplicar la empresa.

    `stripe_subscription_id`/`paypal_subscription_id` (mutuamente excluyentes, petición explícita,
    2026-11-22/23 — periodo de prueba de 7 días): con uno de los dos, se consulta la suscripción
    REAL en la pasarela para saber si está en periodo de prueba — en ese caso NO se ha cobrado nada
    todavía, así que el registro interno de factura/pago se hace por 0€ (nunca se finge un cobro de
    tarifa completa que no ha ocurrido) y `proximo_cobro` se resuelve de la fecha REAL de la
    pasarela, no de un cálculo local aproximado."""
    from src.services.saas import planes as _P

    if not _P.plan(plan):
        return {"ok": False, "error": f"Plan desconocido: {plan}"}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo_aprovisionamiento, plan, id_empresa FROM altas_web_stripe "
                   "WHERE stripe_session_id=%s", (session_id,))
        existente = _fila(cur, cur.fetchone())
        if existente:
            from src.services import provisioning
            from src.services.saas import suscripciones as S
            cfg = provisioning.config_tenant(existente["id_empresa"])
            sus = S.estado(existente["id_empresa"], config=cfg)
            return {"ok": True, "codigo": existente["codigo_aprovisionamiento"],
                    "plan": existente["plan"], "id_empresa": existente["id_empresa"],
                    "proximo_cobro": sus.get("proximo_cobro") if sus else None,
                    "ya_existia": True}

        cuenta = _cuenta_por_email(cur, email)

    from src.services import provisioning

    if cuenta:
        # Cliente que YA tenía cuenta (p. ej. cambia de plan) y vuelve a pasar por Checkout: usa
        # su centro principal existente en vez de crear uno nuevo cada vez — en SU base física
        # (`config_tenant` devuelve `None` para las 3 empresas de antes del aislamiento, que
        # siguen en la compartida sin cambios).
        from src.db.centros import crear_centro, listar_centros
        id_empresa_destino = cuenta["id_empresa_central"]
        cfg_tenant = provisioning.config_tenant(id_empresa_destino)
        centros = listar_centros(id_empresa_destino, config=cfg_tenant) or []
        id_centro = next((c["id_centro"] for c in centros if c.get("es_principal")),
                         centros[0]["id_centro"] if centros else None)
        if not id_centro:
            id_centro = crear_centro(id_empresa_destino, nombre_centro="Centro principal",
                                     es_principal=True, config=cfg_tenant)
    else:
        if not password_hash:
            return {"ok": False, "error": "Falta la contraseña para la cuenta nueva."}
        tenant = provisioning.aprovisionar_tenant_nuevo(nombre_empresa, email)
        if not tenant.get("ok"):
            return {"ok": False, "error": "No se pudo registrar la empresa."}
        id_empresa_destino, id_centro = tenant["id_empresa"], tenant["id_centro"]
        cfg_tenant = provisioning.config_tenant(id_empresa_destino)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cuentas_web_central (email, password_hash, "
                       "id_empresa_central) VALUES (%s,%s,%s)",
                       (email, password_hash, id_empresa_destino))
            conn.commit()

    campo_precio = "precio_anual" if ciclo == "anual" else "precio"
    precio = float(_P.plan(plan)[campo_precio])
    proximo_cobro_real = None
    if stripe_subscription_id:
        try:
            import os

            import stripe
            stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
            sus_stripe = stripe.Subscription.retrieve(stripe_subscription_id)
            if sus_stripe.get("status") == "trialing":
                import datetime as _dt
                precio = 0.0
                fin_periodo = sus_stripe.get("current_period_end")
                if fin_periodo:
                    proximo_cobro_real = _dt.date.fromtimestamp(fin_periodo)
        except Exception as ex:
            logger.warning("No se pudo resolver el estado de prueba de %s en Stripe: %s",
                           stripe_subscription_id, ex)
    elif paypal_subscription_id:
        en_prueba, proximo_cobro_paypal = _resolver_prueba_paypal(paypal_subscription_id)
        if en_prueba:
            precio = 0.0
        proximo_cobro_real = proximo_cobro_paypal
    numero = f"SAAS-{session_id[:20].upper()}"
    if not _activar_plan_pagado(id_empresa_destino, plan, precio=precio, referencia=numero,
                                config=cfg_tenant, ciclo=ciclo, proximo_cobro=proximo_cobro_real):
        return {"ok": False, "error": "No se pudo activar la suscripción."}

    if stripe_customer_id or paypal_subscription_id:
        with obtener_conexion(cfg_tenant) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM suscripciones WHERE id_empresa=%s ORDER BY id DESC LIMIT 1",
                       (id_empresa_destino,))
            sus = _fila(cur, cur.fetchone())
            if sus and stripe_customer_id:
                cur.execute("UPDATE suscripciones SET stripe_customer_id=%s WHERE id=%s",
                           (stripe_customer_id, sus["id"]))
                conn.commit()
            elif sus and paypal_subscription_id:
                cur.execute("UPDATE suscripciones SET paypal_subscription_id=%s WHERE id=%s",
                           (paypal_subscription_id, sus["id"]))
                conn.commit()

    codigo = _generar_codigo_provisioning(id_centro, id_empresa_destino)
    if not codigo:
        return {"ok": False, "error": "No se pudo generar el código de instalación."}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO altas_web_stripe (stripe_session_id, email, id_empresa, id_centro, "
            "codigo_aprovisionamiento, plan, stripe_customer_id, paypal_subscription_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (session_id, email, id_empresa_destino, id_centro, codigo, plan, stripe_customer_id,
             paypal_subscription_id))
        conn.commit()

    logger.info("Alta %s vía %s: empresa=%s email=%s session=%s", plan,
               "PayPal" if paypal_subscription_id else "Stripe Checkout",
               id_empresa_destino, email, session_id)
    from src.services.saas import suscripciones as S
    sus = S.estado(id_empresa_destino, config=cfg_tenant)
    return {"ok": True, "codigo": codigo, "plan": plan, "id_empresa": id_empresa_destino,
            "proximo_cobro": sus.get("proximo_cobro") if sus else None,
            "ya_existia": False}


def confirmar_financiacion(*, session_id, plan, email, nombre_empresa, password_hash,
                           stripe_customer_id=None, setup_intent_id=None,
                           paypal_subscription_id=None) -> dict:
    """Financiación de un plan anual en 4 cuotas trimestrales, sin intereses, con el mismo periodo
    de prueba de 7 días que el resto de planes (reconsiderado 2026-11-22: ya no es mutuamente
    excluyente, la primera cuota se cobra al TERMINAR la prueba, no en el acto).

    Dos pasarelas, mutuamente excluyentes (petición explícita, 2026-11-23 — PayPal en la web
    oficial):
    - Stripe (`stripe_customer_id`+`setup_intent_id`): el Checkout en modo `setup` solo VINCULA un
      método de pago; el cobro real de las 4 cuotas lo hace el `stripe.SubscriptionSchedule` que se
      crea aquí (fase 1 = 4 iteraciones trimestrales a `precio_anual_financiado/4` — descuento
      reducido a 1 mes gratis en vez de 2, petición explícita 2026-11-27 — vía un Price creado al
      vuelo, con `trial_end` a 7 días vista; fase 2 = el precio anual normal de siempre [2 meses
      gratis], sin fin).
    - PayPal (`paypal_subscription_id`): el Plan con sus 3 fases (prueba, 4 cuotas, anual) ya se
      creó y la Suscripción ya se aprobó ANTES de llegar aquí (ver `sitio_oficial.
      _completar_registro_paypal`/`_paypal_crear_plan_financiacion`) — aquí no hace falta crear
      nada más en PayPal, solo resolver si sigue en prueba (igual que `confirmar_pago`) y dar de
      alta la empresa.

    Idempotente por `session_id` (con PayPal, `f"paypal_{subscription_id}"`), igual que
    `confirmar_pago` (con quien comparte toda la lógica de alta de empresa/centro — ver ahí los
    comentarios)."""
    from src.services.saas import planes as _P

    cfg_plan = _P.plan(plan)
    if not cfg_plan:
        return {"ok": False, "error": f"Plan desconocido: {plan}"}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo_aprovisionamiento, plan, id_empresa FROM altas_web_stripe "
                   "WHERE stripe_session_id=%s", (session_id,))
        existente = _fila(cur, cur.fetchone())
        if existente:
            from src.services import provisioning
            from src.services.saas import suscripciones as S
            cfg = provisioning.config_tenant(existente["id_empresa"])
            sus = S.estado(existente["id_empresa"], config=cfg)
            return {"ok": True, "codigo": existente["codigo_aprovisionamiento"],
                    "plan": existente["plan"], "id_empresa": existente["id_empresa"],
                    "proximo_cobro": sus.get("proximo_cobro") if sus else None,
                    "ya_existia": True}

        cuenta = _cuenta_por_email(cur, email)

    schedule = None
    proximo_cobro = None
    if paypal_subscription_id:
        # La financiación por PayPal SIEMPRE llega aquí recién aprobada (la Suscripción, con sus 3
        # fases, se creó justo antes — ver `sitio_oficial._completar_registro_paypal`), así que
        # SIEMPRE está en la fase de prueba todavía — mismo motivo por el que el riel Stripe de
        # abajo nunca comprueba el estado, tampoco hace falta aquí.
        _, proximo_cobro = _resolver_prueba_paypal(paypal_subscription_id)
    else:
        import os

        import stripe
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

        price_id_anual = os.environ.get(f"STRIPE_PRICE_ID_{plan.upper()}_ANUAL")
        if not price_id_anual:
            return {"ok": False, "error": "La financiación no está disponible para este plan todavía."}

        try:
            setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
            metodo_pago = setup_intent.get("payment_method")
            if not metodo_pago:
                return {"ok": False, "error": "No se pudo vincular el método de pago."}
            stripe.PaymentMethod.attach(metodo_pago, customer=stripe_customer_id)
            stripe.Customer.modify(stripe_customer_id,
                                   invoice_settings={"default_payment_method": metodo_pago})
        except Exception as ex:
            logger.error("Resolviendo método de pago tras Setup Checkout (%s): %s", setup_intent_id, ex)
            return {"ok": False, "error": "No se pudo vincular el método de pago."}

    from src.services import provisioning

    if cuenta:
        from src.db.centros import crear_centro, listar_centros
        id_empresa_destino = cuenta["id_empresa_central"]
        cfg_tenant = provisioning.config_tenant(id_empresa_destino)
        centros = listar_centros(id_empresa_destino, config=cfg_tenant) or []
        id_centro = next((c["id_centro"] for c in centros if c.get("es_principal")),
                         centros[0]["id_centro"] if centros else None)
        if not id_centro:
            id_centro = crear_centro(id_empresa_destino, nombre_centro="Centro principal",
                                     es_principal=True, config=cfg_tenant)
    else:
        if not password_hash:
            return {"ok": False, "error": "Falta la contraseña para la cuenta nueva."}
        tenant = provisioning.aprovisionar_tenant_nuevo(nombre_empresa, email)
        if not tenant.get("ok"):
            return {"ok": False, "error": "No se pudo registrar la empresa."}
        id_empresa_destino, id_centro = tenant["id_empresa"], tenant["id_centro"]
        cfg_tenant = provisioning.config_tenant(id_empresa_destino)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cuentas_web_central (email, password_hash, "
                       "id_empresa_central) VALUES (%s,%s,%s)",
                       (email, password_hash, id_empresa_destino))
            conn.commit()

    if not paypal_subscription_id:
        # Petición explícita, 2026-11-27: financiar el anual en 4 cuotas ya NO lleva el mismo
        # descuento (2 meses gratis) que pagarlo de una vez — pasa a 1 mes gratis
        # (`precio_anual_financiado`, ver `services.saas.planes`), un coste ligeramente mayor como
        # incentivo real a pagar el anual íntegro. Esto SOLO afecta a la cuota del año 1; la fase 2
        # de este mismo SubscriptionSchedule (más abajo) sigue usando `STRIPE_PRICE_ID_*_ANUAL`,
        # el precio anual normal con el descuento completo.
        precio_anual_financiado = float(cfg_plan["precio_anual_financiado"])
        cuota = round(precio_anual_financiado / 4, 2)

        import datetime as _dt
        fin_prueba = _dt.datetime.utcnow() + _dt.timedelta(days=7)
        trial_end_ts = int(fin_prueba.timestamp())

        try:
            precio_cuota = stripe.Price.create(
                currency="eur",
                unit_amount=int(round(cuota * 100)),
                recurring={"interval": "month", "interval_count": 3},
                product_data={"name": f"Smart Manager - {plan} (financiado, 4 cuotas trimestrales)"},
            )
            schedule = stripe.SubscriptionSchedule.create(
                customer=stripe_customer_id,
                start_date="now",
                end_behavior="release",
                default_settings={"default_payment_method": metodo_pago},
                phases=[
                    {"items": [{"price": precio_cuota["id"], "quantity": 1}], "iterations": 4,
                     "trial_end": trial_end_ts},
                    {"items": [{"price": price_id_anual, "quantity": 1}]},
                ],
            )
        except Exception as ex:
            logger.error("Creando SubscriptionSchedule de financiación (cliente %s): %s",
                         stripe_customer_id, ex)
            return {"ok": False, "error": "No se pudo programar las cuotas de financiación."}
        # La primera cuota se cobra al terminar la prueba (no ahora), así que aquí no se ha
        # cobrado nada todavía — mismo criterio que la prueba gratuita normal (ver
        # `confirmar_pago`): se registra la factura/pago inicial por 0€, nunca un cobro que no ha
        # ocurrido.
        proximo_cobro = fin_prueba.date()

    numero = f"SAAS-FIN-{session_id[:16].upper()}"
    if not _activar_plan_pagado(id_empresa_destino, plan, precio=0.0, referencia=numero,
                                config=cfg_tenant, ciclo="anual", proximo_cobro=proximo_cobro):
        return {"ok": False, "error": "No se pudo activar la suscripción."}

    if stripe_customer_id or paypal_subscription_id:
        with obtener_conexion(cfg_tenant) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM suscripciones WHERE id_empresa=%s ORDER BY id DESC LIMIT 1",
                       (id_empresa_destino,))
            sus = _fila(cur, cur.fetchone())
            if sus and stripe_customer_id:
                cur.execute("UPDATE suscripciones SET stripe_customer_id=%s WHERE id=%s",
                           (stripe_customer_id, sus["id"]))
                conn.commit()
            elif sus and paypal_subscription_id:
                cur.execute("UPDATE suscripciones SET paypal_subscription_id=%s WHERE id=%s",
                           (paypal_subscription_id, sus["id"]))
                conn.commit()

    codigo = _generar_codigo_provisioning(id_centro, id_empresa_destino)
    if not codigo:
        return {"ok": False, "error": "No se pudo generar el código de instalación."}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO altas_web_stripe (stripe_session_id, email, id_empresa, id_centro, "
            "codigo_aprovisionamiento, plan, stripe_customer_id, paypal_subscription_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (session_id, email, id_empresa_destino, id_centro, codigo, plan, stripe_customer_id,
             paypal_subscription_id))
        conn.commit()

    logger.info("Alta %s financiada en 4 cuotas vía %s: empresa=%s email=%s session=%s%s",
               plan, "PayPal" if paypal_subscription_id else "Stripe", id_empresa_destino, email,
               session_id, f" schedule={schedule.get('id')}" if schedule else "")
    from src.services.saas import suscripciones as S
    sus = S.estado(id_empresa_destino, config=cfg_tenant)
    return {"ok": True, "codigo": codigo, "plan": plan, "id_empresa": id_empresa_destino,
            "proximo_cobro": sus.get("proximo_cobro") if sus else None,
            "ya_existia": False}


def login(email, password) -> dict:
    from werkzeug.security import check_password_hash

    with obtener_conexion() as conn, conn.cursor() as cur:
        cuenta = _cuenta_por_email(cur, email)
    if not cuenta or not check_password_hash(cuenta["password_hash"], password):
        return {"ok": False, "error": "Email o contraseña incorrectos."}
    return {"ok": True, "id_empresa": cuenta["id_empresa_central"]}


def datos_cuenta(id_empresa) -> dict:
    """Códigos de instalación emitidos + ordenadores emparejados (con credencial propia, ver
    `services.provisioning.crear_credencial_db`) + estado de suscripción, para "Mi cuenta"."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT codigo, usado, expira, creado FROM codigos_aprovisionamiento "
            "WHERE id_empresa=%s ORDER BY creado DESC", (id_empresa,))
        cols = [d[0] for d in cur.description]
        codigos = [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in cur.fetchall()]

    from src.services import provisioning
    from src.services.saas import suscripciones as S
    cfg_tenant = provisioning.config_tenant(id_empresa)
    estado = S.estado(id_empresa, config=cfg_tenant)
    instalaciones = provisioning.listar_instalaciones(id_empresa)
    for c in codigos:
        for campo in ("expira", "creado"):
            if c.get(campo):
                c[campo] = str(c[campo])
    for i in instalaciones:
        for campo in ("creado", "ultima_conexion", "revocado_en"):
            if i.get(campo):
                i[campo] = str(i[campo])
    return {"ok": True, "codigos": codigos, "instalaciones": instalaciones, "suscripcion": estado}


def revocar_instalacion(id_instalacion, id_empresa) -> dict:
    """Revoca UN ordenador emparejado — verificando que pertenece a esta empresa antes de tocar
    nada (ver `services.provisioning.revocar_credencial_db`)."""
    from src.services import provisioning
    return provisioning.revocar_credencial_db(id_instalacion, id_empresa)
