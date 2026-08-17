"""Marketplace + Pagos — emisión + conciliación de IBAN virtual (P2). `db`.

Cubre: emitir_iban_virtual pide el IBAN al PSP (simulado sin credenciales), lo vincula a la transacción, es
idempotente, y la conciliación posterior de la transferencia entrante marca FUNDS_HELD.
"""

import pytest

from src.services.pagos_marketplace import conciliacion as CONC, escrow as ESC, operaciones as OP

pytestmark = pytest.mark.db


def _nuevo_tx(db, emp, id_vendedor, cantidad=1, precio=120.0):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lonja_transacciones (id_listado, id_vendedor, id_empresa, cantidad, "
                    "precio_unitario, divisa, tipo, estado) VALUES (0,%s,%s,%s,%s,'EUR','compra_directa',"
                    "'confirmada')", (id_vendedor, emp, cantidad, precio))
        txid = cur.lastrowid
        conn.commit()
        return txid


def _limpia(db, txids):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in txids:
            cur.execute("DELETE FROM pagos_eventos WHERE id_transaccion=%s", (t,))
            cur.execute("DELETE FROM lonja_transacciones WHERE id=%s", (t,))
        conn.commit()


def test_emitir_y_conciliar_iban_virtual(db, fab):
    emp = fab.empresa("EMP iban virtual")
    fab.al_limpiar(lambda: _limpia(db, [tx]))
    tx = _nuevo_tx(db, emp, 9100, cantidad=1, precio=120.0)

    r = OP.emitir_iban_virtual(tx)
    assert r["ok"] and r["iban_virtual_ref"].startswith("SIMIBAN") and r["modo"] == "simulado"
    ref = r["iban_virtual_ref"]
    # Idempotente: no re-emite si ya hay IBAN virtual.
    assert OP.emitir_iban_virtual(tx)["idempotente"] is True

    # Entra la transferencia (webhook/extracto) → concilia a FUNDS_HELD.
    c = CONC.conciliar_transferencia(ref, importe=120.0)
    assert c["ok"] and c["estado_pago"] == "FUNDS_HELD" and c["id_transaccion"] == tx
    assert ESC.estado(tx) == "FUNDS_HELD"
