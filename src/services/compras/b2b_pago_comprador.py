"""
Requisito obligatorio de método de pago verificado para el comprador del Portal B2B (petición
explícita, 2026-11-16: "no puede existir ninguna asimetría frente a lo que se exige a los
proveedores" — el proveedor ya exige Stripe Connect verificado antes de publicar catálogo o
recibir pedidos; esto es el equivalente para el comprador, antes de poder tramitar pedidos).

Arquitectura: un Customer de Stripe NORMAL (no Connect — el comprador paga, no cobra, así que no
hace falta cuenta conectada ni onboarding KYB) con un PaymentMethod guardado y fijado como
`invoice_settings.default_payment_method`. Se verifica con un SetupIntent (la tarjeta la valida de
verdad el banco emisor, SIN cobrar nada) — mismo criterio de "verificación real, nunca fingida" que
`suministradores.py` usa para Stripe Connect, y la misma confirmación en dos fases (nunca se confía
en la redirección por sí sola) que `b2b_escrow.py` usa para el cobro real de los pedidos.

Caché local (`b2b_empresas_pago.verificado`, migr. 0345) — mismo criterio que
`suministradores.stripe_verificado`: `esta_verificado` (el hot path que gatea `b2b_pedidos.
tramitar`) nunca llama a la API de Stripe, solo lee esta tabla.
"""

import logging
import os

from src.db.conexion import obtener_conexion

logger = logging.getLogger("compras.b2b_pago_comprador")

_API = "https://api.stripe.com/v1"


def _req():
    import requests  # import perezoso (degradable)
    return requests


def _auth():
    return (os.getenv("STRIPE_SECRET_KEY") or "", "")


def configurado() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def _fila(cur, r):
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _leer(id_empresa):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_empresas_pago WHERE id_empresa=%s", (id_empresa,))
            return _fila(cur, cur.fetchone())
    except Exception as e:
        logger.error("_leer(%s): %s", id_empresa, e)
        return None


def esta_verificado(id_empresa) -> bool:
    """Lectura rápida de caché local — SIN llamar a Stripe/PayPal. Hot path: gatea
    `b2b_pedidos.tramitar` en cada intento de confirmar carrito. Petición explícita, 2026-11-22:
    PayPal como alternativa — basta con CUALQUIERA de las dos pasarelas verificada (a diferencia
    del proveedor, una empresa SÍ puede verificar las dos si lo necesita para comprar a proveedores
    que cobran por vías distintas — ver `esta_verificado_para`, el gate específico por pasarela que
    usa el checkout para cada proveedor en concreto)."""
    if not id_empresa:
        return False
    fila = _leer(id_empresa)
    return bool(fila and (fila.get("verificado") or fila.get("paypal_verificado")))


def esta_verificado_para(id_empresa, pasarela: str, *, id_suministrador=None) -> bool:
    """¿Verificado en ESA pasarela en concreto ('stripe'|'paypal')? Usado por el checkout para
    confirmar que la empresa puede pagar AL PROVEEDOR CONCRETO de cada línea del carrito — el
    escrow liquida por la pasarela del proveedor, así que la empresa necesita estar verificada en
    esa MISMA pasarela, no basta con "alguna" (ver `esta_verificado`, el gate genérico de
    "¿puedes comprar algo, a quien sea?").

    `id_suministrador` (petición explícita, 2026-11-27 — pago directo sin custodia): para PayPal,
    la verificación ya NO es global — cada proveedor cobra con su propia app de PayPal, así que el
    Vault del comprador está vinculado a ESE proveedor en concreto (`b2b_pago_comprador_proveedor`).
    Sin `id_suministrador`, cae al criterio antiguo (global) por compatibilidad con llamadores que
    no lo pasen."""
    if not id_empresa:
        return False
    if pasarela == "paypal":
        if id_suministrador is not None:
            fila_prov = _leer_proveedor(id_empresa, id_suministrador) or {}
            return bool(fila_prov.get("paypal_verificado"))
        fila = _leer(id_empresa) or {}
        return bool(fila.get("paypal_verificado"))
    fila = _leer(id_empresa) or {}
    return bool(fila.get("verificado"))


def estado(id_empresa) -> dict:
    """Para el panel del comprador: {verificado, tiene_customer, paypal_verificado}.

    `paypal_verificado` (petición explícita, 2026-11-27): ya no es un estado global único — se
    cuenta si la empresa tiene AL MENOS UN proveedor con PayPal ya vinculado
    (`b2b_pago_comprador_proveedor`), como señal de "ya sabe cómo funciona"; el gate real de cada
    pedido sigue siendo `esta_verificado_para(..., id_suministrador=...)`, por proveedor."""
    fila = _leer(id_empresa) or {}
    tiene_algun_paypal = False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM b2b_pago_comprador_proveedor WHERE id_empresa=%s "
                       "AND paypal_verificado=1", (id_empresa,))
            r = cur.fetchone()
            tiene_algun_paypal = bool((r[0] if not isinstance(r, dict) else r["COUNT(*)"]) or 0)
    except Exception as e:
        logger.debug("estado (conteo paypal por proveedor, %s): %s", id_empresa, e)
    return {"verificado": bool(fila.get("verificado")),
           "tiene_customer": bool(fila.get("stripe_customer_id")),
           "paypal_verificado": tiene_algun_paypal}


# ── PayPal por PROVEEDOR (Vault API v3, pago directo sin custodia — petición explícita, ──────────
# 2026-11-27): el Vault guardado está vinculado a la app de PayPal que lo creó — con cada proveedor
# usando SU PROPIA app (`suministradores.credenciales_paypal_de`), un Vault global bajo la app de
# Smart Manager (vía antigua, arriba) ya no permite cobrar a través de la app del proveedor. El
# comprador aprueba el pago con PayPal la primera vez que compra a CADA proveedor nuevo; las
# compras siguientes a ESE MISMO proveedor ya no requieren aprobación (mismo criterio "verificación
# real, nunca fingida" que el resto del módulo).
def _leer_proveedor(id_empresa, id_suministrador) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_pago_comprador_proveedor WHERE id_empresa=%s AND "
                       "id_suministrador=%s", (id_empresa, id_suministrador))
            return _fila(cur, cur.fetchone())
    except Exception as e:
        logger.error("_leer_proveedor(%s, %s): %s", id_empresa, id_suministrador, e)
        return None


def vault_id_paypal_proveedor(id_empresa, id_suministrador) -> str | None:
    """Token de la Vault API de PayPal de esta empresa PARA ESTE PROVEEDOR EN CONCRETO — lo que
    `b2b_escrow.py` pasa como `vault_id` a `retener_fondos` (instanciada con las credenciales de
    ESE MISMO proveedor) para no exigirle al comprador aprobar el pago a mano en cada pedido."""
    fila = _leer_proveedor(id_empresa, id_suministrador) or {}
    return fila.get("paypal_payment_token_id")


def _token_paypal_proveedor(id_suministrador):
    """Token OAuth2 usando las credenciales PROPIAS del proveedor (nunca las globales de Smart
    Manager) — el Vault creado con este token solo sirve para cobrar a través de SU app, que es
    justo lo que se necesita: que el pago nazca y viva en su cuenta."""
    from src.services.compras import suministradores as SUP
    creds = SUP.credenciales_paypal_de(id_suministrador)
    if not creds:
        return None
    try:
        requests = _req()
        import os
        base = ("https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_MODO", "test") != "live"
               else "https://api-m.paypal.com")
        r = requests.post(f"{base}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                          auth=(creds["client_id"], creds["client_secret"]), timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("_token_paypal_proveedor(%s) %s: %s", id_suministrador, r.status_code,
                      r.text[:200])
    except Exception as e:
        logger.error("_token_paypal_proveedor(%s): %s", id_suministrador, e)
    return None


def iniciar_vinculacion_paypal_proveedor(id_empresa, id_suministrador, *, return_url=None,
                                         cancel_url=None) -> dict:
    """Crea un SETUP_TOKEN (Vault API v3) con la app del PROVEEDOR y devuelve el enlace de
    aprobación de PayPal. Devuelve {ok, approve_url, setup_token_id} o {ok: False, error}."""
    import os
    token = _token_paypal_proveedor(id_suministrador)
    if not token:
        return {"ok": False, "error": "paypal_no_configurado_por_el_proveedor"}
    try:
        requests = _req()
        base = ("https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_MODO", "test") != "live"
               else "https://api-m.paypal.com")
        payload = {"payment_source": {"paypal": {
            "usage_type": "MERCHANT",
            "experience_context": {
                "return_url": return_url or "https://smartmanager.local/b2b/paypal/retorno",
                "cancel_url": cancel_url or "https://smartmanager.local/b2b/paypal/cancelado",
            },
        }}}
        r = requests.post(f"{base}/v3/vault/setup-tokens", json=payload,
                          headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"}, timeout=25)
        if r.status_code not in (200, 201):
            logger.warning("iniciar_vinculacion_paypal_proveedor (setup-tokens) %s: %s",
                          r.status_code, r.text[:200])
            return {"ok": False, "error": "no_se_pudo_iniciar_la_verificacion"}
        j = r.json()
        approve_url = next((l.get("href") for l in j.get("links", []) if l.get("rel") == "approve"), None)
        if not approve_url:
            return {"ok": False, "error": "paypal_no_devolvio_enlace_de_aprobacion"}
        return {"ok": True, "approve_url": approve_url, "setup_token_id": j.get("id")}
    except Exception as e:
        logger.error("iniciar_vinculacion_paypal_proveedor: %s", e)
        return {"ok": False, "error": "error_interno"}


def confirmar_vinculacion_paypal_proveedor(id_empresa, id_suministrador, setup_token_id) -> dict:
    """Tras el `return_url` de PayPal — NUNCA se confía en la redirección por sí sola: se crea el
    PAYMENT_TOKEN real (con la app del proveedor) a partir del SETUP_TOKEN. Guardado por PAREJA
    (empresa, proveedor) — ver docstring de esta sección."""
    import os
    if not setup_token_id:
        return {"ok": False, "error": "falta_setup_token"}
    token = _token_paypal_proveedor(id_suministrador)
    if not token:
        return {"ok": False, "error": "paypal_no_configurado_por_el_proveedor"}
    try:
        requests = _req()
        base = ("https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_MODO", "test") != "live"
               else "https://api-m.paypal.com")
        payload = {"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}}
        r = requests.post(f"{base}/v3/vault/payment-tokens", json=payload,
                          headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"}, timeout=25)
        if r.status_code not in (200, 201):
            logger.warning("confirmar_vinculacion_paypal_proveedor (payment-tokens) %s: %s",
                          r.status_code, r.text[:200])
            return {"ok": False, "error": "verificacion_no_completada"}
        payment_token_id = r.json().get("id")
        if not payment_token_id:
            return {"ok": False, "error": "paypal_no_devolvio_token"}
    except Exception as e:
        logger.error("confirmar_vinculacion_paypal_proveedor (payment-tokens): %s", e)
        return {"ok": False, "error": "error_interno"}
    try:
        fila = _leer_proveedor(id_empresa, id_suministrador)
        with obtener_conexion() as conn, conn.cursor() as cur:
            if fila:
                cur.execute(
                    "UPDATE b2b_pago_comprador_proveedor SET paypal_payment_token_id=%s, "
                    "paypal_verificado=1, paypal_verificado_en=NOW() WHERE id_empresa=%s AND "
                    "id_suministrador=%s", (payment_token_id, id_empresa, id_suministrador))
            else:
                cur.execute(
                    "INSERT INTO b2b_pago_comprador_proveedor (id_empresa, id_suministrador, "
                    "paypal_payment_token_id, paypal_verificado, paypal_verificado_en) "
                    "VALUES (%s,%s,%s,1,NOW())",
                    (id_empresa, id_suministrador, payment_token_id))
            conn.commit()
    except Exception as e:
        logger.error("confirmar_vinculacion_paypal_proveedor (BD, %s, %s): %s",
                     id_empresa, id_suministrador, e)
        return {"ok": False, "error": "error_interno"}
    return {"ok": True}


def _crear_customer(id_empresa, *, email=None, nombre=None) -> str | None:
    if not configurado():
        return None
    try:
        requests = _req()
        data = {"metadata[id_empresa]": id_empresa}
        if email:
            data["email"] = email
        if nombre:
            data["name"] = nombre
        r = requests.post(f"{_API}/customers", data=data, auth=_auth(), timeout=25)
        if r.status_code in (200, 201):
            return r.json().get("id")
        logger.warning("_crear_customer %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("_crear_customer: %s", e)
    return None


def iniciar_vinculacion(id_empresa, *, email=None, nombre=None) -> dict:
    """Crea (o reutiliza) el Customer de la empresa + un SetupIntent nuevo. Devuelve
    {ok, client_secret} o {ok: False, error}."""
    if not configurado():
        return {"ok": False, "error": "pago_no_configurado"}
    fila = _leer(id_empresa)
    customer_id = fila.get("stripe_customer_id") if fila else None
    if not customer_id:
        customer_id = _crear_customer(id_empresa, email=email, nombre=nombre)
        if not customer_id:
            return {"ok": False, "error": "no_se_pudo_crear_el_cliente_de_pago"}
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                if fila:
                    cur.execute("UPDATE b2b_empresas_pago SET stripe_customer_id=%s "
                               "WHERE id_empresa=%s", (customer_id, id_empresa))
                else:
                    cur.execute("INSERT INTO b2b_empresas_pago (id_empresa, stripe_customer_id) "
                               "VALUES (%s,%s)", (id_empresa, customer_id))
                conn.commit()
        except Exception as e:
            logger.error("iniciar_vinculacion (guardar customer, %s): %s", id_empresa, e)
            return {"ok": False, "error": "error_interno"}
    try:
        requests = _req()
        r = requests.post(f"{_API}/setup_intents",
                          data={"customer": customer_id, "usage": "off_session"},
                          auth=_auth(), timeout=25)
        if r.status_code not in (200, 201):
            logger.warning("iniciar_vinculacion (setup_intent) %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "error": "no_se_pudo_iniciar_la_verificacion"}
        si = r.json()
        return {"ok": True, "client_secret": si.get("client_secret")}
    except Exception as e:
        logger.error("iniciar_vinculacion (setup_intent): %s", e)
        return {"ok": False, "error": "error_interno"}


def confirmar_vinculacion(id_empresa, setup_intent_id) -> dict:
    """Tras el `return_url` de Stripe.js (`confirmSetup`) — NUNCA se confía en la redirección por
    sí sola: se re-consulta el SetupIntent real en Stripe antes de marcar nada como verificado. Si
    `succeeded`, fija el PaymentMethod resultante como predeterminado del Customer y cachea
    `verificado=1`."""
    if not configurado():
        return {"ok": False, "error": "pago_no_configurado"}
    if not setup_intent_id:
        return {"ok": False, "error": "falta_setup_intent"}
    try:
        requests = _req()
        r = requests.get(f"{_API}/setup_intents/{setup_intent_id}", auth=_auth(), timeout=25)
        if r.status_code != 200:
            logger.warning("confirmar_vinculacion (get) %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "error": "no_se_pudo_verificar"}
        si = r.json()
    except Exception as e:
        logger.error("confirmar_vinculacion (get): %s", e)
        return {"ok": False, "error": "error_interno"}
    if si.get("status") != "succeeded":
        return {"ok": False, "error": f"verificacion_no_completada ({si.get('status')})"}
    customer_id = si.get("customer")
    payment_method_id = si.get("payment_method")
    try:
        requests = _req()
        requests.post(f"{_API}/customers/{customer_id}",
                      data={"invoice_settings[default_payment_method]": payment_method_id},
                      auth=_auth(), timeout=25)
    except Exception as e:
        # No bloquea la verificación: el PaymentMethod ya está adjunto al Customer por el propio
        # SetupIntent aunque esto falle — solo se pierde la comodidad de "usarlo por defecto".
        logger.warning("confirmar_vinculacion (fijar default, %s): %s", customer_id, e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE b2b_empresas_pago SET stripe_payment_method_id=%s, verificado=1, "
                "verificado_en=NOW() WHERE id_empresa=%s", (payment_method_id, id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("confirmar_vinculacion (BD, %s): %s", id_empresa, e)
        return {"ok": False, "error": "error_interno"}
    return {"ok": True}


