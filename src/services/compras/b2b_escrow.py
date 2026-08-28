"""
Custodia de fondos (escrow) para pedidos B2B (Smart Suppliers · Fase C). Orquesta el ciclo de fondos
retenidos de una Transacción Comercial (`transaccion_comercial`, `origen='b2b'`, ver Fase A/B) usando
el motor YA EXISTENTE `PasarelaMarketplace` (`src/services/tpv/pagos/base_marketplace.py`) — Smart
Manager NO custodia fondos: registra el ESTADO y delega la operación real en el PSP (Stripe Connect si
hay credenciales configuradas; simulado en caso contrario — ver `B2B_PASARELA_PROVEEDOR`).

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


def _pasarela():
    """Adaptador de pago a usar. Por defecto SIMULADO (decisión explícita del usuario para esta
    implementación): construye y prueba todo el flujo sin credenciales reales. Activar Stripe Connect
    real no requiere tocar código: basta con fijar B2B_PASARELA_PROVEEDOR=stripe_connect y configurar
    sus credenciales (mismo mecanismo que ya usa el resto de pasarelas, `pagos.pasarela.configurar`,
    protegido con step-up MFA)."""
    from src.services.tpv.pagos.registry import clase_de
    proveedor = os.getenv("B2B_PASARELA_PROVEEDOR", "simulado_mkt")
    clase = clase_de(proveedor) or clase_de("simulado_mkt")
    return clase({})


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
def iniciar_retencion(id_tx, *, actor=None) -> dict:
    """CONFIRMADA → PAGADA (pedido) / FUNDS_HELD (escrow). La llamada al PSP se hace ANTES de tomar
    el bloqueo de fila (nunca red dentro de una transacción de BD)."""
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
    importe = float(tx.get("total") or 0)
    idem = f"b2b-retener-{id_tx}"
    res = _pasarela().retener_fondos(
        importe=importe, divisa=tx.get("moneda") or "EUR",
        vendedor_account=sup.get("cuenta_conectada_id"), comision=0,
        referencia=f"b2b_tx_{id_tx}", idem_key=idem, id_empresa=tx["id_empresa"])
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}

    with transaccion() as conn, conn.cursor() as cur:
        esc = _leer_escrow(cur, id_tx)
        if esc and esc["estado_pago"] != "PAYMENT_PENDING":
            return {"ok": True, "idempotente": True, "estado_pago": esc["estado_pago"]}
        if esc is None:
            cur.execute("INSERT INTO b2b_escrow (id_tx, estado_pago, psp_payment_ref, "
                       "importe_retenido, divisa, retenido_en) VALUES (%s,'FUNDS_HELD',%s,%s,%s,NOW())",
                       (id_tx, res.get("payment_ref"), importe, tx.get("moneda") or "EUR"))
        else:
            cur.execute("UPDATE b2b_escrow SET estado_pago='FUNDS_HELD', psp_payment_ref=%s, "
                       "importe_retenido=%s, retenido_en=NOW() WHERE id_tx=%s",
                       (res.get("payment_ref"), importe, id_tx))
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='PAGADA' WHERE id_tx=%s AND estado='CONFIRMADA'",
            (id_tx,))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")  # provoca ROLLBACK real
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], "CONFIRMADA", "PAGADA", actor)
        _ledger_anotar(cur, id_tx, "RETENCION", importe, actor or "sistema", res.get("payment_ref"))
    return {"ok": True, "estado": "PAGADA", "estado_pago": "FUNDS_HELD"}


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
        cur.execute("SELECT estado_pago, psp_payment_ref FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None
    if not esc:
        return {"ok": False, "error": "sin_fondos_retenidos"}
    if esc["estado_pago"] == "IN_DISPUTE":
        return {"ok": False, "error": "disputa_abierta_no_se_puede_liberar"}

    res = _pasarela().liberar_fondos(payment_ref=esc["psp_payment_ref"], idem_key=f"b2b-liberar-{id_tx}")
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


def cancelar_y_reembolsar(id_tx, *, motivo, actor=None) -> dict:
    """Cancela el pedido. Si no había fondos retenidos todavía (BORRADOR/CONFIRMADA), cancela sin más.
    Si ya se habían retenido, pide el reembolso al PSP antes de marcar CANCELADA — nunca deja el
    dinero retenido sin un pedido activo al que corresponda (Prohibido dejar transacciones colgadas).
    NO aplica aquí la política de plazos/perecederos (Fase D, `cancelaciones.py`) — este es solo el
    mecanismo financiero una vez la cancelación ya está aprobada."""
    tx = _leer_tx(id_tx)
    if not tx:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if tx["estado"] == "CANCELADA":
        return {"ok": True, "idempotente": True}
    if tx["estado"] not in ("BORRADOR", "CONFIRMADA", "PAGADA", "PREPARANDO"):
        return {"ok": False, "error": f"estado_invalido_para_cancelar ({tx['estado']})"}

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago, psp_payment_ref, importe_retenido FROM b2b_escrow "
                   "WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        esc = _fila(cur, row) if row else None

    referencia_reembolso = None
    if esc and esc["estado_pago"] in ("FUNDS_HELD", "IN_FULFILLMENT"):
        res = _pasarela().reembolsar(payment_ref=esc["psp_payment_ref"],
                                     importe=float(esc["importe_retenido"] or 0),
                                     idem_key=f"b2b-reembolso-{id_tx}")
        if not res.get("ok"):
            return {"ok": False, "error": res.get("mensaje", "psp_error")}
        referencia_reembolso = res.get("refund_ref")

    with transaccion() as conn, conn.cursor() as cur:
        if esc and esc["estado_pago"] in ("FUNDS_HELD", "IN_FULFILLMENT"):
            cur.execute("UPDATE b2b_escrow SET estado_pago='REFUNDED' WHERE id_tx=%s", (id_tx,))
            _ledger_anotar(cur, id_tx, "REEMBOLSO", float(esc["importe_retenido"] or 0),
                          actor or "sistema", referencia_reembolso)
        actualizadas = cur.execute(
            "UPDATE transaccion_comercial SET estado='CANCELADA' WHERE id_tx=%s AND estado=%s",
            (id_tx, tx["estado"]))
        if not actualizadas:
            raise RuntimeError("estado_de_pedido_cambio_concurrentemente")
        _registrar_evento_tx(cur, id_tx, tx["id_empresa"], tx["estado"], "CANCELADA", actor,
                             payload_extra={"motivo": motivo})
    return {"ok": True, "estado": "CANCELADA"}


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
