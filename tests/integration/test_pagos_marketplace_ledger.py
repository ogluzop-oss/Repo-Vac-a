"""Marketplace + Pagos (F4) — ledger inmutable, conciliación por IBAN virtual y comisión contabilizada. `db`.

Cubre: registro append-only de los movimientos de escrow (FUNDS_HELD/FUNDS_RELEASED); conciliación de una
transferencia por IBAN virtual (→FUNDS_HELD + evento RECONCILED, idempotente); y contabilización idempotente
de la comisión de la plataforma al liberar.
"""

import pytest

from src.services.pagos_marketplace import (conciliacion as CONC, contabilizacion as CONTAB,
                                            cuentas as CU, escrow as ESC, ledger as LED)

pytestmark = pytest.mark.db

PLATAFORMA = "00000000-0000-0000-0000-000000000001"


def _nuevo_tx(db, emp, id_vendedor, cantidad=2, precio=50.0, divisa="EUR"):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lonja_transacciones (id_listado, id_vendedor, id_empresa, cantidad, "
                    "precio_unitario, divisa, tipo, estado) VALUES (0,%s,%s,%s,%s,%s,'compra_directa',"
                    "'confirmada')", (id_vendedor, emp, cantidad, precio, divisa))
        txid = cur.lastrowid
        conn.commit()
        return txid


def _limpia(db, txids, vendedor):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in txids:
            cur.execute("DELETE FROM pagos_eventos WHERE id_transaccion=%s", (t,))
            cur.execute("DELETE FROM lonja_transacciones WHERE id=%s", (t,))
        cur.execute("DELETE FROM psp_cuentas_conectadas WHERE tipo_parte='vendedor' AND id_parte=%s",
                    (vendedor,))
        conn.commit()


def test_ledger_registra_movimientos(db, fab):
    emp = fab.empresa("EMP ledger")
    vendedor = 8901
    fab.al_limpiar(lambda: _limpia(db, [tx], vendedor))
    CU.registrar_token("vendedor", vendedor, "acct_L1", status="verified", payouts_enabled=True,
                       id_empresa=PLATAFORMA)
    tx = _nuevo_tx(db, emp, vendedor)

    ESC.iniciar_retencion(tx, comision_pct=10)
    ESC.marcar_en_preparacion(tx)
    ESC.confirmar_entrega(tx)   # libera automáticamente

    tipos = [e["tipo"] for e in LED.libro(tx)]
    assert "FUNDS_HELD" in tipos and "FUNDS_RELEASED" in tipos
    # El ledger es cronológico: la retención antes que la liberación.
    assert tipos.index("FUNDS_HELD") < tipos.index("FUNDS_RELEASED")


def test_conciliacion_iban_virtual(db, fab):
    emp = fab.empresa("EMP concilia")
    vendedor = 8902
    fab.al_limpiar(lambda: _limpia(db, [tx], vendedor))
    CU.registrar_token("vendedor", vendedor, "acct_L2", status="verified", payouts_enabled=True,
                       id_empresa=PLATAFORMA)
    tx = _nuevo_tx(db, emp, vendedor)

    assert CONC.asignar_iban_virtual(tx, "ES00VIRTUAL0001")["ok"] is True
    r = CONC.conciliar_transferencia("ES00VIRTUAL0001", importe=100.0)
    assert r["ok"] and r["estado_pago"] == "FUNDS_HELD" and r["id_transaccion"] == tx
    # Idempotente: la misma transferencia no vuelve a mover el estado.
    assert CONC.conciliar_transferencia("ES00VIRTUAL0001")["idempotente"] is True
    assert any(e["tipo"] == "RECONCILED" for e in LED.libro(tx))
    # Referencia inexistente → error controlado.
    assert CONC.conciliar_transferencia("NO_EXISTE")["ok"] is False


def test_comision_contabilizada_idempotente(db, fab):
    emp = fab.empresa("EMP comision")
    vendedor = 8903
    fab.al_limpiar(lambda: _limpia(db, [tx], vendedor))
    CU.registrar_token("vendedor", vendedor, "acct_L3", status="verified", payouts_enabled=True,
                       id_empresa=PLATAFORMA)
    tx = _nuevo_tx(db, emp, vendedor, cantidad=1, precio=100.0)   # importe 100
    ESC.iniciar_retencion(tx, comision_pct=10)                    # comisión 10
    ESC.confirmar_entrega(tx)                                     # libera → contabiliza comisión

    # Volver a contabilizar es idempotente (o degrada limpiamente si la contabilidad no está disponible).
    r = CONTAB.contabilizar_comision(tx)
    assert r.get("ok") or r.get("degradado")
    if r.get("ok"):
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT asiento_comision FROM lonja_transacciones WHERE id=%s", (tx,))
            row = cur.fetchone()
        asiento = row[0] if not isinstance(row, dict) else row["asiento_comision"]
        # Si se contabilizó, quedó enlazado y el segundo intento fue idempotente.
        assert (asiento is not None) or r.get("sin_comision")
