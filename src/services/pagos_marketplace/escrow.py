"""
Máquina de estados ESCROW sobre las transacciones de la Lonja (F2 — Marketplace + Pagos).

Orquesta el ciclo de fondos custodiados de una `lonja_transacciones` usando el motor F1
(`PasarelaMarketplace`). Smart Manager NO custodia fondos: registra el ESTADO y delega la operación real
en el PSP (Stripe Connect; simulado sin credenciales).

Flujo:
  (venta/adjudicación) → iniciar_retencion → FUNDS_HELD
                       → marcar_en_preparacion → IN_FULFILLMENT
   (comprador conforme) → confirmar_entrega → DELIVERY_CONFIRMED → [auto] liberar → FUNDS_RELEASED
   (desacuerdo)         → abrir_disputa → IN_DISPUTE
   (resolución)         → reembolsar → REFUNDED

Garantías: cada transición valida el estado de origen, es IDEMPOTENTE (si ya está en destino, no repite),
re-verifica con `SELECT … FOR UPDATE` antes de escribir, y la llamada al PSP usa una `idem_key` estable
(evita dobles cargos). La llamada de red NO se hace dentro del bloqueo. El asiento contable de doble partida
y la conciliación por IBAN virtual son de F4.
"""

import logging

# Reutiliza los helpers de la Lonja (conexión, transacción con bloqueo, auditoría) — N7, sin duplicar.
from src.services.lonja._common import _audit, _conn, _tx, _uno

logger = logging.getLogger("pagos_marketplace.escrow")

ESTADOS = ("PAYMENT_PENDING", "FUNDS_HELD", "IN_FULFILLMENT", "DELIVERY_CONFIRMED",
           "FUNDS_RELEASED", "IN_DISPUTE", "REFUNDED")


def _leer(id_transaccion) -> dict | None:
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM lonja_transacciones WHERE id=%s", (id_transaccion,))
        return _uno(cur)


def estado(id_transaccion) -> str | None:
    t = _leer(id_transaccion)
    return (t or {}).get("estado_pago")


# ── Sincronización dirigida por webhook (local, SIN llamar al PSP) ─────────────
_TERMINALES = ("FUNDS_RELEASED", "REFUNDED")


def tx_por_payment_ref(payment_ref) -> dict | None:
    """Localiza la transacción por la referencia de pago del PSP (la usa el webhook Connect)."""
    if not payment_ref:
        return None
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM lonja_transacciones WHERE psp_payment_ref=%s LIMIT 1", (payment_ref,))
        return _uno(cur)


def set_estado_local(id_transaccion, nuevo, *, transfer_ref=None, motivo="webhook") -> dict:
    """Fija el estado de pago desde un webhook (el PSP ya ejecutó la operación real). Idempotente y
    seguro ante desorden: no revierte estados terminales (FUNDS_RELEASED/REFUNDED)."""
    if nuevo not in ESTADOS:
        return {"ok": False, "error": "estado_invalido"}
    with _tx() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago FROM lonja_transacciones WHERE id=%s FOR UPDATE", (id_transaccion,))
        t = _uno(cur)
        if not t:
            return {"ok": False, "error": "transaccion_no_encontrada"}
        actual = t.get("estado_pago")
        if actual == nuevo:
            return {"ok": True, "idempotente": True, "estado_pago": nuevo}
        if actual in _TERMINALES:
            return {"ok": True, "ignorado": True, "estado_pago": actual}
        sets, params = ["estado_pago=%s"], [nuevo]
        if nuevo == "FUNDS_RELEASED":
            sets.append("released_en=NOW()")
        if transfer_ref:
            sets.append("psp_transfer_ref=%s"); params.append(transfer_ref)
        params.append(id_transaccion)
        cur.execute("UPDATE lonja_transacciones SET " + ", ".join(sets) + " WHERE id=%s", tuple(params))
    _audit(f"ESCROW_WEBHOOK_{nuevo}", f"tx={id_transaccion} {actual}->{nuevo} ({motivo})",
           tabla="lonja_transacciones")
    return {"ok": True, "estado_pago": nuevo}


def _adaptador(id_empresa):
    from src.services.pagos_marketplace import psp
    return psp.adaptador(id_empresa)


def _idem(t) -> str:
    return t.get("idem_key_pago") or f"lonja-tx-{t['id']}"


# ── Inicio de la retención (escrow) ──────────────────────────────────────────
def iniciar_retencion(id_transaccion, *, comision_pct=None, usuario=None) -> dict:
    """Autoriza y retiene el importe de la transacción con destino al vendedor y comisión de plataforma.
    Idempotente: si ya está retenida (o más allá), devuelve el estado actual sin recobrar."""
    from src.services.pagos_marketplace import cuentas
    t = _leer(id_transaccion)
    if not t:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if t.get("estado_pago") in ("FUNDS_HELD", "IN_FULFILLMENT", "DELIVERY_CONFIRMED",
                                "FUNDS_RELEASED"):
        return {"ok": True, "idempotente": True, "estado_pago": t["estado_pago"],
                "payment_ref": t.get("psp_payment_ref")}
    if t.get("estado_pago") in ("REFUNDED",):
        return {"ok": False, "error": "transaccion_reembolsada"}

    emp = t["id_empresa"]
    cuenta = cuentas.account_conectado("vendedor", t["id_vendedor"])
    if not cuenta or not cuenta.get("account_id"):
        return {"ok": False, "error": "vendedor_sin_cobros_conectados"}

    importe = float(t.get("cantidad") or 0) * float(t.get("precio_unitario") or 0)
    pct = float(comision_pct if comision_pct is not None else _comision_pct(emp) or 0)
    comision = round(importe * pct / 100.0, 4)
    idem = _idem(t)

    res = _adaptador(emp).retener_fondos(
        importe=importe, divisa=t.get("divisa") or "EUR", vendedor_account=cuenta["account_id"],
        comision=comision, referencia=f"lonja_tx_{t['id']}", idem_key=idem, id_empresa=emp)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}

    # Re-verifica con bloqueo y escribe el estado final (no repite si otro hilo se adelantó).
    with _tx() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago FROM lonja_transacciones WHERE id=%s FOR UPDATE", (t["id"],))
        actual = (_uno(cur) or {}).get("estado_pago")
        if actual in ("FUNDS_HELD", "IN_FULFILLMENT", "DELIVERY_CONFIRMED", "FUNDS_RELEASED"):
            return {"ok": True, "idempotente": True, "estado_pago": actual}
        cur.execute("UPDATE lonja_transacciones SET estado_pago='FUNDS_HELD', psp_payment_ref=%s, "
                    "comision_importe=%s, idem_key_pago=%s, held_en=NOW() WHERE id=%s",
                    (res.get("payment_ref"), comision, idem, t["id"]))
    _audit("ESCROW_HELD", f"tx={t['id']} ref={res.get('payment_ref')} comision={comision}",
           tabla="lonja_transacciones")
    return {"ok": True, "estado_pago": "FUNDS_HELD", "payment_ref": res.get("payment_ref"),
            "comision": comision, "modo": _adaptador(emp).modo()}


def _comision_pct(id_empresa) -> float:
    try:
        from src.db import pagos as pagos_db
        cfg = pagos_db.obtener_config(id_empresa) or {}
        return float(cfg.get("comision_pct") or 0)
    except Exception:
        return 0.0


# ── Transiciones simples (sin llamada al PSP) ────────────────────────────────
def _transicion_simple(id_transaccion, destino, fuentes, accion) -> dict:
    with _tx() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago FROM lonja_transacciones WHERE id=%s FOR UPDATE", (id_transaccion,))
        t = _uno(cur)
        if not t:
            return {"ok": False, "error": "transaccion_no_encontrada"}
        actual = t.get("estado_pago")
        if actual == destino:
            return {"ok": True, "idempotente": True, "estado_pago": destino}
        if actual not in fuentes:
            return {"ok": False, "error": f"transicion_invalida:{actual}->{destino}"}
        cur.execute("UPDATE lonja_transacciones SET estado_pago=%s WHERE id=%s", (destino, id_transaccion))
    _audit(accion, f"tx={id_transaccion} {actual}->{destino}", tabla="lonja_transacciones")
    return {"ok": True, "estado_pago": destino}


def marcar_en_preparacion(id_transaccion) -> dict:
    return _transicion_simple(id_transaccion, "IN_FULFILLMENT", ("FUNDS_HELD",), "ESCROW_IN_FULFILLMENT")


def abrir_disputa(id_transaccion, motivo=None) -> dict:
    r = _transicion_simple(id_transaccion, "IN_DISPUTE",
                           ("FUNDS_HELD", "IN_FULFILLMENT", "DELIVERY_CONFIRMED"), "ESCROW_DISPUTE")
    if r.get("ok") and motivo:
        _audit("ESCROW_DISPUTE_MOTIVO", f"tx={id_transaccion}: {motivo}", tabla="lonja_transacciones")
    return r


def confirmar_entrega(id_transaccion, *, liberar_auto=True) -> dict:
    r = _transicion_simple(id_transaccion, "DELIVERY_CONFIRMED",
                           ("FUNDS_HELD", "IN_FULFILLMENT"), "ESCROW_DELIVERY_CONFIRMED")
    if r.get("ok") and not r.get("idempotente") and liberar_auto:
        return liberar(id_transaccion)
    return r


# ── Transiciones con llamada al PSP (liberar / reembolsar) ────────────────────
def liberar(id_transaccion) -> dict:
    """Libera los fondos retenidos al vendedor (capture del PaymentIntent). Idempotente."""
    t = _leer(id_transaccion)
    if not t:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if t.get("estado_pago") == "FUNDS_RELEASED":
        return {"ok": True, "idempotente": True, "estado_pago": "FUNDS_RELEASED"}
    if t.get("estado_pago") not in ("DELIVERY_CONFIRMED",):
        return {"ok": False, "error": f"transicion_invalida:{t.get('estado_pago')}->FUNDS_RELEASED"}
    if not t.get("psp_payment_ref"):
        return {"ok": False, "error": "sin_referencia_de_pago"}

    res = _adaptador(t["id_empresa"]).liberar_fondos(payment_ref=t["psp_payment_ref"], idem_key=_idem(t))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}
    with _tx() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago FROM lonja_transacciones WHERE id=%s FOR UPDATE", (t["id"],))
        if (_uno(cur) or {}).get("estado_pago") == "FUNDS_RELEASED":
            return {"ok": True, "idempotente": True, "estado_pago": "FUNDS_RELEASED"}
        cur.execute("UPDATE lonja_transacciones SET estado_pago='FUNDS_RELEASED', psp_transfer_ref=%s, "
                    "released_en=NOW() WHERE id=%s", (res.get("transfer_ref"), t["id"]))
    _audit("ESCROW_RELEASED", f"tx={t['id']} transfer={res.get('transfer_ref')}",
           tabla="lonja_transacciones")
    return {"ok": True, "estado_pago": "FUNDS_RELEASED", "transfer_ref": res.get("transfer_ref")}


def reembolsar(id_transaccion, *, importe=None) -> dict:
    """Reembolsa (total o parcial) una retención. Válido desde FUNDS_HELD/IN_FULFILLMENT/IN_DISPUTE."""
    t = _leer(id_transaccion)
    if not t:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if t.get("estado_pago") == "REFUNDED":
        return {"ok": True, "idempotente": True, "estado_pago": "REFUNDED"}
    if t.get("estado_pago") not in ("FUNDS_HELD", "IN_FULFILLMENT", "IN_DISPUTE"):
        return {"ok": False, "error": f"transicion_invalida:{t.get('estado_pago')}->REFUNDED"}
    if not t.get("psp_payment_ref"):
        return {"ok": False, "error": "sin_referencia_de_pago"}

    res = _adaptador(t["id_empresa"]).reembolsar(payment_ref=t["psp_payment_ref"], importe=importe,
                                                 idem_key=f"{_idem(t)}-refund")
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "psp_error")}
    with _tx() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_pago FROM lonja_transacciones WHERE id=%s FOR UPDATE", (t["id"],))
        if (_uno(cur) or {}).get("estado_pago") == "REFUNDED":
            return {"ok": True, "idempotente": True, "estado_pago": "REFUNDED"}
        cur.execute("UPDATE lonja_transacciones SET estado_pago='REFUNDED' WHERE id=%s", (t["id"],))
    _audit("ESCROW_REFUNDED", f"tx={t['id']} refund={res.get('refund_ref')}", tabla="lonja_transacciones")
    return {"ok": True, "estado_pago": "REFUNDED", "refund_ref": res.get("refund_ref")}
