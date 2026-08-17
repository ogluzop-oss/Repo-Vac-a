"""
Ledger inmutable de pagos (F4 — Marketplace + Pagos).

Registro APPEND-ONLY (event sourcing) de cada movimiento de fondos de una transacción de la Lonja. Es la
fuente de verdad de la trazabilidad: nunca se actualiza ni se borra una fila, solo se AÑADEN eventos
(FUNDS_HELD, FUNDS_RELEASED, IN_DISPUTE, REFUNDED, RECONCILED…). Degradable: si el registro falla, NO
rompe la transición de escrow (el estado sigue en `lonja_transacciones` + auditoría).
"""

import json
import logging

logger = logging.getLogger("pagos_marketplace.ledger")

TIPOS = ("FUNDS_HELD", "FUNDS_RELEASED", "IN_DISPUTE", "REFUNDED", "RECONCILED", "PAYMENT_PENDING")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def registrar(id_transaccion, tipo, *, importe=0, comision=0, payment_ref=None, transfer_ref=None,
              divisa="EUR", payload=None, id_empresa=None) -> int | None:
    """Añade un evento inmutable. Devuelve el id o None (degradable)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO pagos_eventos (id_empresa, id_transaccion, tipo, importe, comision, divisa, "
                "payment_ref, transfer_ref, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (emp, int(id_transaccion), tipo, float(importe or 0), float(comision or 0),
                 (divisa or "EUR").upper(), payment_ref, transfer_ref,
                 json.dumps(payload, ensure_ascii=False) if payload else None))
            eid = cur.lastrowid
            c.commit()
        return eid
    except Exception as e:
        logger.warning("ledger.registrar(tx=%s,%s): %s", id_transaccion, tipo, e)
        return None


def libro(id_transaccion) -> list:
    """Eventos de una transacción, en orden cronológico (append-only)."""
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, tipo, importe, comision, divisa, payment_ref, transfer_ref, payload, "
                        "creado_en FROM pagos_eventos WHERE id_transaccion=%s ORDER BY id", (id_transaccion,))
            return _filas(cur)
    except Exception as e:
        logger.error("ledger.libro(%s): %s", id_transaccion, e)
        return []


def listar(id_empresa=None, limite=200) -> list:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_transaccion, tipo, importe, comision, divisa, payment_ref, "
                        "transfer_ref, creado_en FROM pagos_eventos WHERE id_empresa=%s "
                        "ORDER BY id DESC LIMIT %s", (emp, int(limite)))
            return _filas(cur)
    except Exception as e:
        logger.error("ledger.listar: %s", e)
        return []
