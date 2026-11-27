"""
Custodia de fondos (escrow) para pedidos B2B (Smart Suppliers · Fase C). Orquesta el ciclo de fondos
retenidos de una Transacción Comercial (`transaccion_comercial`, `origen='b2b'`, ver Fase A/B) usando
el motor YA EXISTENTE `PasarelaMarketplace` (`src/services/tpv/pagos/base_marketplace.py`) — Smart
Manager NO custodia fondos en ningún momento: registra el ESTADO (retenido/preparando/enviado/
liberado) y delega la operación real de dinero en el PSP de CADA proveedor (Stripe Connect con su
cuenta conectada, o PayPal con SUS PROPIAS credenciales de app — petición explícita, 2026-11-27: el
pago va siempre directo de la empresa compradora a la cuenta del proveedor, nunca a través de la
cuenta de Smart Manager; simulado si no hay credenciales — ver `B2B_PASARELA_PROVEEDOR`).

Inspirado en el `escrow.py` retirado (commit 408548b), pero sobre `b2b_escrow`/`transaccion_comercial`
en vez de `lonja_transacciones`: NO hay motor de transacciones paralelo. El ciclo de vida del PEDIDO
sigue siendo el de `services.comercio_digital.transacciones` (BORRADOR…CANCELADA); este módulo AÑADE el
seguimiento de la CUSTODIA DE FONDOS de esa misma transacción y avanza su estado cuando corresponde,
dentro de la MISMA transacción de base de datos (atomicidad real: si el cambio de estado del pedido no
se pudiera aplicar, el movimiento de fondos tampoco queda registrado).

Flujo:
  CONFIRMADA → iniciar_retencion       → pedido PAGADA,     escrow FUNDS_HELD
             → marcar_en_preparacion   → pedido PREPARANDO, escrow IN_FULFILLMENT
             → marcar_enviado          → pedido ENVIADA     (escrow sigue IN_FULFILLMENT)
  (conforme) → confirmar_entrega       → pedido ENTREGADA,  escrow DELIVERY_CONFIRMED → [auto] FUNDS_RELEASED
  (expira)   → liberar_pendientes_por_expiracion (job programado) → mismo efecto, motivo='expiracion_plazo'
  (cancelado)→ cancelar_y_reembolsar   → pedido CANCELADA,  escrow REFUNDED (si había fondos retenidos)

Garantías: cada transición valida el estado de origen (ignora — no repite — si ya está en destino:
IDEMPOTENTE ante reintentos de red), usa `SELECT…FOR UPDATE` antes de escribir, y la llamada al PSP usa
un `idem_key` estable (evita dobles cargos). La llamada de red al PSP NUNCA se hace dentro del bloqueo
de fila. El ledger es APPEND-ONLY y cada fila incluye el hash de la anterior (cadena verificable).
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("compras.b2b_escrow")

ESTADOS = ("PAYMENT_PENDING", "FUNDS_HELD", "IN_FULFILLMENT", "DELIVERY_CONFIRMED",
          "FUNDS_RELEASED", "IN_DISPUTE", "REFUNDED")
_TERMINALES = ("FUNDS_RELEASED", "REFUNDED")
DIAS_VENTANA_REVISION = 3  # plazo legal de revisión antes de liberar por expiración (requisito 5)


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _pasarela(pasarela_nombre: str = "stripe", id_suministrador=None):
    """Adaptador de pago a usar — resuelto POR TRANSACCIÓN (petición explícita, 2026-11-22: PayPal
    como alternativa a Stripe — cada proveedor cobra por UNA pasarela concreta, ver
    `suministradores.pasarela_cobro_de`/columna `b2b_escrow.pasarela`, migr. 0356). `pasarela_nombre`
    es 'stripe'|'paypal'.

    PayPal SIN Partner Program NI custodia de Smart Manager (petición explícita, 2026-11-27 —
    rediseño sobre el de 2026-11-23): se instancia con las credenciales PROPIAS del proveedor
    (`suministradores.credenciales_paypal_de(id_suministrador)`), nunca con las globales de Smart
    Manager — así la Orden se crea y captura directamente en SU cuenta (ver el docstring de
    `tpv.pagos.paypal_connect`). Sin `id_suministrador` o sin credenciales propias configuradas,
    degrada a simulado (nunca finge un estado real ni usa, por error, la cuenta de Smart Manager
    para cobrar a un tercero).

    `B2B_PASARELA_PROVEEDOR` sigue siendo el interruptor maestro de siempre (decisión explícita del
    usuario, 2026-11-16: por defecto SIMULADO para TODA la plataforma, pase lo que pase con las
    credenciales — activar cobros reales exige fijarlo explícitamente en el entorno del servidor,
    nunca ocurre solo porque existan credenciales). Con el interruptor en real, cada transacción usa
    la pasarela de SU proveedor — y esa pasarela en concreto degrada a simulado igualmente si a
    ELLA le faltan credenciales (nunca finge un estado real).

    Hueco real encontrado y corregido 2026-11-16: antes se instanciaba la clase con un config VACÍO
    (`clase({})`), así que `PasarelaStripeConnect.configurado()` (que mira `self.config['api_key']`)
    SIEMPRE devolvía False — activar la pasarela real no habría bastado nunca para que llegara a
    usarse, aunque las credenciales estuvieran bien puestas."""
    from src.services.tpv.pagos.registry import clase_de
    modo_real = os.getenv("B2B_PASARELA_PROVEEDOR", "simulado_mkt") != "simulado_mkt"
    if modo_real and pasarela_nombre == "paypal":
        creds = None
        if id_suministrador is not None:
            from src.services.compras import suministradores as SUP
            creds = SUP.credenciales_paypal_de(id_suministrador)
        if creds:
            clase = clase_de("paypal_connect")
            if clase:
                return clase({"api_key": creds["client_id"], "api_secret": creds["client_secret"],
                             "modo": os.getenv("PAYPAL_MODO", "test")})
    elif modo_real:
        api_key = os.getenv("STRIPE_SECRET_KEY")
        if api_key:
            clase = clase_de("stripe_connect")
            if clase:
                return clase({"api_key": api_key})
    return clase_de("simulado_mkt")({})


def _leer_escrow(cur, id_tx):
    cur.execute("SELECT * FROM b2b_escrow WHERE id_tx=%s FOR UPDATE", (id_tx,))
    row = cur.fetchone()
    return _fila(cur, row) if row else None


def _leer_tx(id_tx) -> dict | None:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        return _fila(cur, row) if row else None


def estado(id_tx) -> dict | None:
    """Estado combinado del pedido + su custodia de fondos (o None si el pedido no existe)."""
    tx = _leer_tx(id_tx)
    if not tx:
        return None
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None
    return {"pedido_estado": tx["estado"], "escrow": esc}


def _hash_fila(id_tx, tipo, monto, actor, ts_str, hash_previo, referencia_psp):
    # Formato canónico de `monto`: al escribir es un float de Python (p. ej. 37.5), al releer para
    # verificar es un Decimal de MySQL (37.50) — sin normalizar a ".2f" ambos, el hash nunca cuadraría
    # aunque el valor numérico fuera idéntico. Bug real detectado al probar verificar_ledger().
    monto_str = f"{float(monto):.2f}"
    base = f"{id_tx}|{tipo}|{monto_str}|{actor}|{ts_str}|{hash_previo or ''}|{referencia_psp or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ledger_anotar(cur, id_tx, tipo, monto, actor, referencia_psp=None):
    """INSERT append-only dentro de la MISMA transacción que el cambio de estado que lo origina: si
    esa transacción hace rollback, el movimiento tampoco queda anotado (nunca hay un asiento huérfano
    de un cambio de estado que no llegó a confirmarse)."""
    cur.execute("SELECT hash_actual FROM b2b_escrow_ledger WHERE id_tx=%s ORDER BY id DESC LIMIT 1",
               (id_tx,))
    row = cur.fetchone()
    hash_previo = (row[0] if not isinstance(row, dict) else row["hash_actual"]) if row else None
    # Precisión de segundo (no microsegundos) para que el hash sea reconstruible tras el round-trip
    # por la columna DATETIME de MySQL, que no conserva microsegundos.
    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hash_actual = _hash_fila(id_tx, tipo, monto, actor, ts_str, hash_previo, referencia_psp)
    cur.execute("INSERT INTO b2b_escrow_ledger (id_tx, tipo, monto, actor, ts, hash_previo, "
               "hash_actual, referencia_psp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
               (id_tx, tipo, monto, actor, ts_str, hash_previo, hash_actual, referencia_psp))


def verificar_ledger(id_tx) -> bool:
    """Recorre el ledger de una transacción y comprueba que la cadena de hashes es íntegra: si algún
    movimiento histórico se alterase o borrase, la cadena dejaría de cuadrar y esta función lo detecta."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT tipo, monto, actor, ts, hash_previo, hash_actual, referencia_psp "
                   "FROM b2b_escrow_ledger WHERE id_tx=%s ORDER BY id ASC", (id_tx,))
        filas = [_fila(cur, r) for r in cur.fetchall()]
    previo = None
    for f in filas:
        ts = f["ts"]
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts)
        if f["hash_previo"] != previo:
            return False
        esperado = _hash_fila(id_tx, f["tipo"], f["monto"], f["actor"], ts_str, previo,
                              f["referencia_psp"])
        if f["hash_actual"] != esperado:
            return False
        previo = f["hash_actual"]
    return True


# ── Ciclo de vida ──────────────────────────────────────────────────────────────
def _marcar_pagada(id_tx, tx, *, payment_ref, importe, comision, recargo_comprador=0.0,
                   actor=None, pasarela="stripe") -> dict:
    """Tail compartido CONFIRMADA → PAGADA (pedido) / FUNDS_HELD (escrow) — extraído de la antigua
    `iniciar_retencion` monolítica (2026-11-16) para que lo compartan 3 caminos: el modo simulado
    (confirma al instante, sin tarjeta real que esperar), `confirmar_pago_tras_retorno` (Stripe real,
    tras verificar que la tarjeta autorizó de verdad) y la propia `iniciar_retencion` (legada).
    `comision` = comisión del PROVEEDOR (significado de siempre); `recargo_comprador` (columna nueva,
    migr. 0352, 2026-11-21) = recargo propio de la empresa compradora — las dos son INDEPENDIENTES
    entre sí (ver `comisiones_b2b`), ya no se asume que valgan lo mismo. `pasarela` ('stripe'|
    'paypal', migr. 0356, 2026-11-22) — con qué PSP se retuvieron estos fondos, reutilizado por
    las operaciones posteriores de este mismo pedido."""
    with transaccion() as conn, conn.cursor() as cur:
        esc = _leer_escrow(cur, id_tx)
        if esc and esc["estado_pago"] not in ("PAYMENT_PENDING",):
            return {"ok": True, "idempotente": True, "estado_pago": esc["estado_pago"]}
        if esc is None:
            cur.execute("INSERT INTO b2b_escrow (id_tx, estado_pago, psp_payment_ref, "
                       "importe_retenido, comision, recargo_comprador, divisa, pasarela, retenido_en) "
                       "VALUES (%s,'FUNDS_HELD',%s,%s,%s,%s,%s,%s,NOW())",
                       (id_tx, payment_ref, importe, comision, recargo_comprador,
                        tx.get("moneda") or "EUR", pasarela))
        else:
            cur.execute("UPDATE b2b_escrow SET estado_pago='FUNDS_HELD', psp_payment_ref=%s, "
                       "importe_retenido=%s, comision=%s, recargo_comprador=%s, pasarela=%s, "
                       "retenido_en=NOW() WHERE id_tx=%s",
                       (payment_ref, importe, comision, recargo_comprador, pasarela, id_tx))
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='PAGADA' WHERE id_tx=%s AND estado='CONFIRMADA'",
            (id_tx,))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")  # provoca ROLLBACK real
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], "CONFIRMADA", "PAGADA", actor)
        _ledger_anotar(cur, id_tx, "RETENCION", importe, actor or "sistema", payment_ref)
    return {"ok": True, "estado": "PAGADA", "estado_pago": "FUNDS_HELD"}


def preparar_pago(id_tx, *, actor=None) -> dict:
    """Primer paso del cobro real de un pedido B2B (petición explícita, 2026-11-16 — antes no
    existía NINGÚN punto que iniciara esto: ver el hallazgo en `portal_empresa_b2b.pagina_pago`).
    Crea (o reutiliza, si el comprador recargó la página sin completar el pago) el PaymentIntent en
    Stripe Connect y devuelve su `client_secret` para que el checkout embeba el Payment Element de
    Stripe — el pedido/escrow NO pasan a PAGADA/FUNDS_HELD aquí todavía (eso solo ocurre cuando
    Stripe confirma que la tarjeta autorizó de verdad, ver `confirmar_pago_tras_retorno`).

    Con la pasarela SIMULADA (sin credenciales reales / desarrollo), no hay `client_secret` que
    confirmar — se marca PAGADA de inmediato, igual que el comportamiento siempre tenido en este
    modo (mismo criterio ya usado en el resto de pasarelas simuladas de la app)."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "PAGADA":
        return {"ok": True, "idempotente": True, "estado": "PAGADA"}
    if tx["estado"] != "CONFIRMADA":
        return {"ok": False, "error": f"estado_invalido_para_pagar ({tx['estado']})"}
    id_suministrador = tx.get("id_suministrador")
    if not id_suministrador:
        return {"ok": False, "error": "pedido_sin_proveedor_asignado"}

    from src.services.compras import suministradores as SUP
    # Pasarela resuelta POR ESTE PROVEEDOR EN CONCRETO (petición explícita, 2026-11-22 — PayPal
    # como alternativa a Stripe): se fija aquí, una sola vez, y el resto de operaciones de este
    # pedido (liberar/cancelar/reembolsar) reutilizan la MISMA — nunca se vuelve a derivar del
    # proveedor más adelante (que podría haber cambiado de pasarela mientras tanto).
    pasarela_nombre = SUP.pasarela_cobro_de(id_suministrador) or "stripe"

    with obtener_conexion() as conn, conn.cursor() as cur:
        esc_previo = _leer_escrow(cur, id_tx)
    if esc_previo and esc_previo.get("estado_pago") == "PAYMENT_PENDING" and esc_previo.get("psp_payment_ref"):
        # Ya se había creado un PaymentIntent antes (el comprador volvió a la página de pago sin
        # completarla) — se recupera su client_secret en vez de crear un cargo nuevo por duplicado.
        # Reutiliza la pasarela YA fijada en esa fila (nunca la recién resuelta), por si el
        # proveedor cambiara de pasarela entre medias.
        estado_psp = _pasarela(esc_previo.get("pasarela") or pasarela_nombre,
                               id_suministrador=id_suministrador).obtener_payment_intent(
            esc_previo["psp_payment_ref"])
        if estado_psp.get("ok") and estado_psp.get("client_secret"):
            return {"ok": True, "client_secret": estado_psp["client_secret"],
                   "payment_ref": esc_previo["psp_payment_ref"], "requiere_pago": True}

    sup = SUP.obtener(id_suministrador) or {}
    importe = float(tx.get("total") or 0)
    # Comisión de plataforma (petición explícita, 2026-11-16; corregida 2026-11-21 para que las dos
    # exenciones sean TOTALMENTE INDEPENDIENTES: la empresa compradora paga su PROPIO recargo salvo
    # que ELLA MISMA tenga suscripción activa — el estado del proveedor es irrelevante para ella, y
    # viceversa. Confirmado con el usuario: no hay ningún modo de "eximir" a una parte por la
    # suscripción de la otra; cada una se ahorra su 2,5% ÚNICAMENTE con su propia suscripción —
    # nunca se revela al uno que el otro también paga/no paga el suyo).
    # Mecánica (petición explícita, 2026-11-27 — pago directo sin custodia: "el pago debe
    # efectuarse directamente entre las cuentas de la empresa compradora y la empresa proveedora,
    # sin intermediarios"): hoy `comision_proveedor` es SIEMPRE 0 (comisión eliminada por completo,
    # ver `comisiones_b2b.py` — la nueva fuente de ingresos de los portales es el Plan de Pago,
    # `services/portal_plan.py`, totalmente independiente de esta transacción). `recargo_comprador`
    # (si lo hubiera) se sigue cobrando aparte por Stripe directo a la empresa compradora, nunca
    # mezclado con el pago al proveedor. Con Stripe Connect, `comision_plataforma` viajaría como
    # Application Fee de una "destination charge" (mecanismo de Stripe, sigue existiendo por si se
    # reactivara una comisión); con PayPal NO hay ningún mecanismo de reparto dentro de la Orden —
    # el proveedor cobra con SU PROPIA app, así que Smart Manager no puede tomar nada de esta
    # transacción en concreto (coherente con que hoy sea siempre 0 para PayPal).
    from src.services.compras import comisiones_b2b
    comision = comisiones_b2b.calcular_proveedor(id_suministrador, importe)
    recargo_comprador = comisiones_b2b.calcular_comprador(tx.get("id_empresa"), importe)
    importe_cobro = round(importe + recargo_comprador, 2)
    comision_plataforma = round(recargo_comprador + comision, 2)
    vault_id = None
    if pasarela_nombre == "paypal":
        from src.services.compras import b2b_pago_comprador as PAGO
        vault_id = PAGO.vault_id_paypal_proveedor(tx["id_empresa"], id_suministrador)
    idem = f"b2b-preparar-{id_tx}"
    res = _pasarela(pasarela_nombre, id_suministrador=id_suministrador).retener_fondos(
        importe=importe_cobro, divisa=tx.get("moneda") or "EUR",
        vendedor_account=sup.get("cuenta_conectada_id"),
        comision=comision_plataforma, referencia=f"b2b_tx_{id_tx}", idem_key=idem,
        id_empresa=tx["id_empresa"], vault_id=vault_id)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}

    client_secret = res.get("client_secret")
    if not client_secret:
        # Pasarela simulada (o PayPal, que nunca devuelve client_secret — autoriza directamente
        # vía el vault_id, sin Payment Element que embeber): `retener_fondos` ya devuelve el pago
        # como retenido de inmediato. `importe`/`comision`/`recargo_comprador` (NO los de cobro/
        # combinados) son los que se guardan en `b2b_escrow` — representan el pedido/el recargo de
        # CADA lado por separado, no el importe bruto cobrado a la tarjeta.
        return _marcar_pagada(id_tx, tx, payment_ref=res.get("payment_ref"), importe=importe,
                              comision=comision, recargo_comprador=recargo_comprador, actor=actor,
                              pasarela=pasarela_nombre)

    with obtener_conexion() as conn, conn.cursor() as cur:
        esc = _leer_escrow(cur, id_tx)
        if esc is None:
            cur.execute("INSERT INTO b2b_escrow (id_tx, estado_pago, psp_payment_ref, "
                       "importe_retenido, comision, recargo_comprador, divisa, pasarela) "
                       "VALUES (%s,'PAYMENT_PENDING',%s,%s,%s,%s,%s,%s)",
                       (id_tx, res.get("payment_ref"), importe, comision, recargo_comprador,
                        tx.get("moneda") or "EUR", pasarela_nombre))
        else:
            cur.execute("UPDATE b2b_escrow SET estado_pago='PAYMENT_PENDING', psp_payment_ref=%s, "
                       "importe_retenido=%s, comision=%s, recargo_comprador=%s, pasarela=%s "
                       "WHERE id_tx=%s",
                       (res.get("payment_ref"), importe, comision, recargo_comprador,
                        pasarela_nombre, id_tx))
        conn.commit()
    return {"ok": True, "client_secret": client_secret, "payment_ref": res.get("payment_ref"),
           "requiere_pago": True}


def confirmar_pago_tras_retorno(id_tx, *, actor=None) -> dict:
    """Segundo paso: se llama cuando Stripe redirige al comprador de vuelta tras completar (o
    abandonar) el formulario de pago (`return_url` del Payment Element). NUNCA se confía en que la
    redirección en sí signifique éxito — se consulta el estado REAL del PaymentIntent en Stripe, y
    solo si quedó de verdad autorizado (`requires_capture`: la tarjeta retuvo el importe) se
    transiciona el pedido a PAGADA / el escrow a FUNDS_HELD."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "PAGADA":
        return {"ok": True, "idempotente": True, "estado": "PAGADA"}
    with obtener_conexion() as conn, conn.cursor() as cur:
        esc = _leer_escrow(cur, id_tx)
    if not esc or not esc.get("psp_payment_ref"):
        return {"ok": False, "error": "pago_no_iniciado"}
    estado_psp = _pasarela(esc.get("pasarela") or "stripe",
                           id_suministrador=tx.get("id_suministrador")).obtener_payment_intent(
        esc["psp_payment_ref"])
    if not estado_psp.get("ok"):
        return {"ok": False, "error": estado_psp.get("mensaje", "psp_error")}
    if estado_psp.get("status") not in ("requires_capture", "succeeded"):
        return {"ok": False, "error": "pago_no_completado", "status_psp": estado_psp.get("status")}
    return _marcar_pagada(id_tx, tx, payment_ref=esc["psp_payment_ref"],
                          importe=float(esc.get("importe_retenido") or tx.get("total") or 0),
                          comision=float(esc.get("comision") or 0),
                          recargo_comprador=float(esc.get("recargo_comprador") or 0), actor=actor,
                          pasarela=esc.get("pasarela") or "stripe")


def iniciar_retencion(id_tx, *, actor=None) -> dict:
    """@deprecated (2026-11-16, Strangler): conservada tal cual (mismo comportamiento de siempre:
    retiene y confirma en UNA sola llamada, sin dar oportunidad a que el comprador confirme una
    tarjeta real) para cualquier llamador directo que pudiera existir — pero el checkout real del
    Portal Empresa usa el flujo de 2 pasos `preparar_pago` + `confirmar_pago_tras_retorno`, el único
    que de verdad puede recoger una tarjeta con Stripe real (3D Secure incluido). Nunca se llegó a
    invocar desde ningún punto de la UI antes de este cambio (hallazgo real, ver el checkout nuevo)."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "PAGADA":
        return {"ok": True, "idempotente": True, "estado": "PAGADA"}
    if tx["estado"] != "CONFIRMADA":
        return {"ok": False, "error": f"estado_invalido_para_retener ({tx['estado']})"}
    id_suministrador = tx.get("id_suministrador")
    if not id_suministrador:
        return {"ok": False, "error": "pedido_sin_proveedor_asignado"}

    from src.services.compras import suministradores as SUP
    sup = SUP.obtener(id_suministrador) or {}
    pasarela_nombre = SUP.pasarela_cobro_de(id_suministrador) or "stripe"
    importe = float(tx.get("total") or 0)
    # Mismos dos recargos independientes que `preparar_pago` (ver su comentario completo) —
    # mantenido aquí por si algún llamador directo de este método @deprecated sigue existiendo.
    from src.services.compras import comisiones_b2b
    comision = comisiones_b2b.calcular_proveedor(id_suministrador, importe)
    recargo_comprador = comisiones_b2b.calcular_comprador(tx.get("id_empresa"), importe)
    importe_cobro = round(importe + recargo_comprador, 2)
    comision_plataforma = round(recargo_comprador + comision, 2)
    vault_id = None
    if pasarela_nombre == "paypal":
        from src.services.compras import b2b_pago_comprador as PAGO
        vault_id = PAGO.vault_id_paypal_proveedor(tx["id_empresa"], id_suministrador)
    idem = f"b2b-retener-{id_tx}"
    res = _pasarela(pasarela_nombre, id_suministrador=id_suministrador).retener_fondos(
        importe=importe_cobro, divisa=tx.get("moneda") or "EUR",
        vendedor_account=sup.get("cuenta_conectada_id"),
        comision=comision_plataforma, referencia=f"b2b_tx_{id_tx}", idem_key=idem,
        id_empresa=tx["id_empresa"], vault_id=vault_id)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}
    return _marcar_pagada(id_tx, tx, payment_ref=res.get("payment_ref"), importe=importe,
                          comision=comision, recargo_comprador=recargo_comprador, actor=actor,
                          pasarela=pasarela_nombre)


def marcar_en_preparacion(id_tx, *, actor=None) -> dict:
    return _transicion_simple(id_tx, desde="PAGADA", hasta="PREPARANDO",
                              escrow_desde="FUNDS_HELD", escrow_hasta="IN_FULFILLMENT", actor=actor)


def marcar_enviado(id_tx, *, actor=None) -> dict:
    return _transicion_simple(id_tx, desde="PREPARANDO", hasta="ENVIADA", actor=actor)


def confirmar_entrega(id_tx, *, actor=None, motivo="confirmacion_comprador") -> dict:
    """ENVIADA → ENTREGADA + libera los fondos retenidos (DELIVERY_CONFIRMED → FUNDS_RELEASED). Si el
    escrow ya está en IN_DISPUTE, se rechaza: una disputa abierta bloquea la liberación automática
    (requisito 5/6 — la disputa se resuelve por Incidencias/Devoluciones, no aquí)."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "ENTREGADA":
        return {"ok": True, "idempotente": True, "estado": "ENTREGADA"}
    if tx["estado"] != "ENVIADA":
        return {"ok": False, "error": f"estado_invalido_para_confirmar_entrega ({tx['estado']})"}
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None
    if not esc:
        return {"ok": False, "error": "sin_fondos_retenidos"}
    if esc["estado_pago"] == "IN_DISPUTE":
        return {"ok": False, "error": "disputa_abierta_no_se_puede_liberar"}

    pasarela_nombre = esc.get("pasarela") or "stripe"
    # Pago directo sin custodia (petición explícita, 2026-11-27): con PayPal, la Orden ya se creó y
    # autorizó con las credenciales PROPIAS del proveedor (ver `_pasarela`), así que el dinero YA
    # está en su cuenta — `liberar_fondos` solo captura, nunca hace falta un Payout posterior (a
    # diferencia del modelo de custodia anterior, retirado).
    res = _pasarela(pasarela_nombre, id_suministrador=tx.get("id_suministrador")).liberar_fondos(
        payment_ref=esc["psp_payment_ref"], idem_key=f"b2b-liberar-{id_tx}")
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}

    with transaccion() as conn, conn.cursor() as cur:
        cur.execute("SELECT importe_retenido FROM b2b_escrow WHERE id_tx=%s FOR UPDATE", (id_tx,))
        row = cur.fetchone()
        importe = float((row[0] if not isinstance(row, dict) else row["importe_retenido"]) or 0)
        cur.execute("UPDATE b2b_escrow SET estado_pago='FUNDS_RELEASED', psp_transfer_ref=%s, "
                   "liberado_en=NOW(), motivo_liberacion=%s WHERE id_tx=%s",
                   (res.get("transfer_ref"), motivo, id_tx))
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='ENTREGADA' WHERE id_tx=%s AND estado='ENVIADA'",
            (id_tx,))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], "ENVIADA", "ENTREGADA", actor)
        _ledger_anotar(cur, id_tx, "LIBERACION", importe, actor or motivo, res.get("transfer_ref"))
    return {"ok": True, "estado": "ENTREGADA", "estado_pago": "FUNDS_RELEASED"}


def liberar_pendientes_por_expiracion(dias: int = DIAS_VENTANA_REVISION) -> dict:
    """Job programado (requisito 5: "...o expira el tiempo legal de revisión"). Libera los fondos de
    pedidos ENVIADA cuyo envío lleva más de `dias` sin confirmación del comprador y sin disputa
    abierta. Nunca libera fondos en IN_DISPUTE."""
    limite = datetime.now() - timedelta(days=dias)
    liberados, fallidos = 0, 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tc.id_tx FROM transaccion_comercial tc JOIN b2b_escrow e ON e.id_tx=tc.id_tx "
                "WHERE tc.estado='ENVIADA' AND e.estado_pago='IN_FULFILLMENT' AND tc.actualizada<=%s",
                (limite,))
            ids = [r[0] if not isinstance(r, dict) else r["id_tx"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("liberar_pendientes_por_expiracion (consulta): %s", e)
        return {"liberados": 0, "fallidos": 0, "error": str(e)}
    for id_tx in ids:
        r = confirmar_entrega(id_tx, actor="scheduler", motivo="expiracion_plazo")
        if r.get("ok"):
            liberados += 1
        else:
            fallidos += 1
            logger.warning("liberar_pendientes_por_expiracion(%s): %s", id_tx, r.get("error"))
    return {"liberados": liberados, "fallidos": fallidos}


def abrir_disputa(id_tx, *, actor=None) -> dict:
    """Bloquea la liberación automática de fondos (manual o por expiración) mientras se tramita una
    reclamación por Incidencias/Devoluciones (requisito 6 — la resolución no vive aquí)."""
    with transaccion() as conn, conn.cursor() as cur:
        esc = _leer_escrow(cur, id_tx)
        if not esc:
            return {"ok": False, "error": "sin_fondos_retenidos"}
        if esc["estado_pago"] in _TERMINALES:
            return {"ok": False, "error": f"escrow_ya_en_estado_terminal ({esc['estado_pago']})"}
        if esc["estado_pago"] == "IN_DISPUTE":
            return {"ok": True, "idempotente": True}
        cur.execute("UPDATE b2b_escrow SET estado_pago='IN_DISPUTE' WHERE id_tx=%s", (id_tx,))
        _ledger_anotar(cur, id_tx, "DISPUTA_ABIERTA", 0, actor or "sistema")
    return {"ok": True, "estado_pago": "IN_DISPUTE"}


def cancelar_y_reembolsar(id_tx, *, motivo, actor=None, recargo_pct: float = 0) -> dict:
    """Cancela el pedido. Si no había fondos retenidos todavía (BORRADOR/CONFIRMADA), cancela sin más.
    Si ya se habían retenido, pide el reembolso al PSP antes de marcar CANCELADA — nunca deja el
    dinero retenido sin un pedido activo al que corresponda (Prohibido dejar transacciones colgadas).
    `recargo_pct` (0-100): penalización de cancelación tardía que la política (Fase D,
    `cancelaciones.politica`) ya calcula — si es > 0, se reembolsa solo la parte restante y se anota el
    recargo como movimiento propio en el ledger (nunca se "pierde" en el redondeo sin dejar rastro).
    NO decide aquí SI se puede cancelar/qué recargo aplica — eso es la política; esto es solo el
    mecanismo financiero una vez la cancelación ya está aprobada."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "CANCELADA":
        return {"ok": True, "idempotente": True}
    if tx["estado"] not in ("BORRADOR", "CONFIRMADA", "PAGADA", "PREPARANDO"):
        return {"ok": False, "error": f"estado_invalido_para_cancelar ({tx['estado']})"}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago, psp_payment_ref, importe_retenido, comision, "
                   "recargo_comprador, pasarela FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None

    referencia_reembolso = None
    importe_recargo = 0.0
    importe_reembolso = 0.0
    if esc and esc["estado_pago"] in ("FUNDS_HELD", "IN_FULFILLMENT"):
        # `importe_total` para el LEDGER = lo realmente autorizado/anulado en Stripe (pedido + el
        # recargo PROPIO del comprador, si aplica — ver `preparar_pago`; el recargo del proveedor
        # NUNCA se cobra a la tarjeta del comprador, así que no entra aquí), no solo el pedido — sin
        # esto, el ledger subestimaría el importe anulado cuando la empresa compradora no tenía
        # suscripción activa.
        importe_total = round(float(esc["importe_retenido"] or 0) +
                              float(esc.get("recargo_comprador") or 0), 2)
        pct = max(0.0, min(100.0, float(recargo_pct or 0)))
        importe_recargo = round(importe_total * pct / 100.0, 2)
        importe_reembolso = round(importe_total - importe_recargo, 2)
        # FUNDS_HELD/IN_FULFILLMENT son SIEMPRE una autorización sin capturar (capture_method=manual;
        # la única captura real ocurre en confirmar_entrega → liberar_fondos). Stripe rechaza un
        # reembolso sobre un PaymentIntent no capturado — hay que ANULARLO (cancelar), no reembolsarlo.
        # Si hay recargo de cancelación tardía, no hay cobro real que ajustar: no se puede cancelar
        # "parcialmente" una autorización, así que el recargo no tiene nada que retener de verdad.
        res = _pasarela(esc.get("pasarela") or "stripe",
                        id_suministrador=tx.get("id_suministrador")).cancelar(
            payment_ref=esc["psp_payment_ref"], idem_key=f"b2b-cancelar-{id_tx}")
        if not res.get("ok"):
            return {"ok": False, "error": res.get("mensaje", "psp_error")}
        referencia_reembolso = res.get("refund_ref")

    with transaccion() as conn, conn.cursor() as cur:
        if esc and esc["estado_pago"] in ("FUNDS_HELD", "IN_FULFILLMENT"):
            cur.execute("UPDATE b2b_escrow SET estado_pago='REFUNDED' WHERE id_tx=%s", (id_tx,))
            _ledger_anotar(cur, id_tx, "REEMBOLSO", importe_reembolso, actor or "sistema",
                          referencia_reembolso)
            if importe_recargo > 0:
                _ledger_anotar(cur, id_tx, "RECARGO_CANCELACION", importe_recargo, actor or "sistema")
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='CANCELADA' WHERE id_tx=%s AND estado=%s",
            (id_tx, tx["estado"]))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], tx["estado"], "CANCELADA", actor,
                             payload_extra={"motivo": motivo})
    return {"ok": True, "estado": "CANCELADA"}


def resolver_disputa_con_reembolso(id_tx, *, motivo, actor=None) -> dict:
    """Resuelve una disputa YA ABIERTA (`abrir_disputa`) con reembolso íntegro de los fondos que
    seguían en custodia (IN_DISPUTE): a diferencia de `cancelar_y_reembolsar` (autoservicio, solo antes
    de ENVIADA), esta es una resolución MEDIADA — el pedido puede llevar ya ENVIADA/ENTREGADA — por eso
    exige que la disputa esté abierta primero (no es un atajo para cancelar sin pasar por Incidencias/
    Devoluciones). Sin recargo: una disputa resuelta a favor del comprador no lleva penalización."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "CANCELADA":
        return {"ok": True, "idempotente": True}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago, psp_payment_ref, importe_retenido, comision, "
                   "recargo_comprador, pasarela FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None
    if not esc or esc["estado_pago"] != "IN_DISPUTE":
        return {"ok": False, "error": f"disputa_no_abierta (estado_pago={esc['estado_pago'] if esc else None})"}

    # Reembolso ÍNTEGRO de lo realmente cobrado a la tarjeta del comprador (pedido + su PROPIO
    # recargo, si aplica — ver `preparar_pago`; el recargo del proveedor nunca se le cobró a él, así
    # que no entra aquí), no solo el pedido.
    importe_reembolso = round(float(esc["importe_retenido"] or 0) +
                              float(esc.get("recargo_comprador") or 0), 2)
    res = _pasarela(esc.get("pasarela") or "stripe",
                    id_suministrador=tx.get("id_suministrador")).reembolsar(
        payment_ref=esc["psp_payment_ref"], importe=importe_reembolso,
        idem_key=f"b2b-disputa-reembolso-{id_tx}")
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}

    with transaccion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE b2b_escrow SET estado_pago='REFUNDED' WHERE id_tx=%s", (id_tx,))
        _ledger_anotar(cur, id_tx, "REEMBOLSO_DISPUTA", importe_reembolso, actor or "sistema",
                      res.get("refund_ref"))
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='CANCELADA' WHERE id_tx=%s AND estado=%s",
            (id_tx, tx["estado"]))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], tx["estado"], "CANCELADA", actor,
                             payload_extra={"motivo": motivo, "via": "disputa"})
    return {"ok": True, "estado": "CANCELADA", "reembolso": importe_reembolso}


# ── Internos ───────────────────────────────────────────────────────────────────
def _transicion_simple(id_tx, *, desde, hasta, actor=None, escrow_desde=None, escrow_hasta=None) -> dict:
    """Transición de estado del pedido SIN llamada al PSP (marcar en preparación / enviado): solo
    mueve el puntero de estado, dentro de una única transacción atómica."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == hasta:
        return {"ok": True, "idempotente": True, "estado": hasta}
    if tx["estado"] != desde:
        return {"ok": False, "error": f"estado_invalido (esperado {desde}, actual {tx['estado']})"}
    with transaccion() as conn, conn.cursor() as cur:
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado=%s WHERE id_tx=%s AND estado=%s",
            (hasta, id_tx, desde))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")
        if escrow_desde and escrow_hasta:
            cur.execute("UPDATE b2b_escrow SET estado_pago=%s WHERE id_tx=%s AND estado_pago=%s",
                       (escrow_hasta, id_tx, escrow_desde))
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], desde, hasta, actor)
    return {"ok": True, "estado": hasta}


def _registrar_evento_tx(cur, id_tx, id_empresa, desde, hasta, actor, payload_extra=None):
    """Anota el cambio de estado del PEDIDO en `transaccion_eventos` (la misma tabla que usa
    `services.comercio_digital.transacciones` — no se crea un registro de auditoría paralelo; los
    eventos generados aquí aparecen igual en `transacciones.eventos()`/`reconstruir()`)."""
    import json
    payload = {"origen": "b2b_escrow"}
    if payload_extra:
        payload.update(payload_extra)
    cur.execute("INSERT INTO transaccion_eventos (id_tx, id_empresa, tipo_evento, estado_desde, "
               "estado_hasta, actor, payload) VALUES (%s,%s,%s,%s,%s,%s,%s)",
               (id_tx, id_empresa, f"Tx{hasta.title()}", desde, hasta, actor,
                json.dumps(payload, ensure_ascii=False)))


def registrar_jobs_escrow(id_empresa=None):
    """Registra el job programado de liberación por expiración de plazo (requisito 5). Degradable: si
    el Scheduler no está disponible, el resto del flujo de escrow sigue funcionando igual (la
    liberación manual por `confirmar_entrega` no depende de este job)."""
    try:
        from src.services import scheduler
        scheduler.registrar("b2b_escrow_liberacion", lambda: liberar_pendientes_por_expiracion())
        scheduler.registrar_job("b2b_escrow_liberacion", intervalo_horas=24,
                                descripcion="Smart Suppliers: liberación de fondos B2B por expiración de plazo")
    except Exception as e:
        logger.debug("registrar_jobs_escrow: %s", e)
