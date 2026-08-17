"""
Conciliación por IBAN virtual (F4 — Marketplace + Pagos).

Para pagos de gran volumen por TRANSFERENCIA, el PSP asigna un IBAN virtual único por operación/comprador.
Cuando entra la transferencia, un webhook (o un extracto) notifica a Smart Manager, que localiza la
transacción por ese IBAN virtual y marca los fondos como retenidos (FUNDS_HELD) SIN intervención humana.

Reutiliza el motor de escrow (`escrow.set_estado_local`) y el ledger inmutable (`ledger`). La EMISIÓN del
IBAN virtual la hace el PSP (adaptador F1, `crear_iban_virtual`, degradable); aquí se guarda su referencia
y se concilia la entrada.
"""

import logging

logger = logging.getLogger("pagos_marketplace.conciliacion")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def asignar_iban_virtual(id_transaccion, referencia, id_empresa=None) -> dict:
    """Vincula una referencia de IBAN virtual a la transacción (para conciliar su transferencia entrante)."""
    if not referencia:
        return {"ok": False, "error": "referencia_vacia"}
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_transacciones SET iban_virtual_ref=%s WHERE id=%s",
                        (referencia, id_transaccion))
            ok = cur.rowcount > 0
            c.commit()
        return {"ok": ok, "iban_virtual_ref": referencia}
    except Exception as e:
        logger.error("asignar_iban_virtual: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def conciliar_transferencia(iban_virtual_ref, *, importe=None, id_empresa=None) -> dict:
    """Concilia una transferencia entrante: localiza la transacción por su IBAN virtual y marca FUNDS_HELD.
    Idempotente (si ya estaba retenida/avanzada, no repite)."""
    from src.services.lonja._common import _uno
    from src.services.pagos_marketplace import escrow, ledger
    if not iban_virtual_ref:
        return {"ok": False, "error": "referencia_vacia"}
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_empresa, estado_pago, divisa FROM lonja_transacciones "
                        "WHERE iban_virtual_ref=%s LIMIT 1", (iban_virtual_ref,))
            t = _uno(cur)
    except Exception as e:
        logger.error("conciliar_transferencia: %s", e)
        return {"ok": False, "error": str(e)[:120]}
    if not t:
        return {"ok": False, "error": "sin_transaccion_para_iban_virtual"}

    r = escrow.set_estado_local(t["id"], "FUNDS_HELD", motivo="iban_virtual")
    if r.get("ok") and not r.get("idempotente") and not r.get("ignorado"):
        ledger.registrar(t["id"], "RECONCILED", importe=float(importe or 0), divisa=t.get("divisa") or "EUR",
                         payload={"iban_virtual_ref": iban_virtual_ref}, id_empresa=t["id_empresa"])
    return {"ok": bool(r.get("ok")), "id_transaccion": t["id"], "estado_pago": r.get("estado_pago"),
            "idempotente": r.get("idempotente", False)}
