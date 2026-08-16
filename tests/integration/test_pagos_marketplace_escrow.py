"""Marketplace + Pagos (F2) — máquina de estados ESCROW sobre lonja_transacciones. `db`.

Cubre: retención (FUNDS_HELD + comisión + ref PSP), idempotencia de la retención, ciclo feliz
(preparación → confirmar entrega → liberación automática = FUNDS_RELEASED), rama de disputa + reembolso,
y el guard de "vendedor sin cobros conectados".
"""

import pytest

from src.services.pagos_marketplace import cuentas as CU, escrow as ESC

pytestmark = pytest.mark.db

PLATAFORMA = "00000000-0000-0000-0000-000000000001"


def _limpia(db, emp, txids, vendedor):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in txids:
            cur.execute("DELETE FROM lonja_transacciones WHERE id=%s", (t,))
        cur.execute("DELETE FROM psp_cuentas_conectadas WHERE tipo_parte='vendedor' AND id_parte=%s",
                    (vendedor,))
        conn.commit()


def _nuevo_tx(db, emp, id_vendedor, **kw):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO lonja_transacciones (id_listado, id_vendedor, id_empresa, cantidad, "
                    "precio_unitario, divisa, tipo, estado) VALUES (0,%s,%s,%s,%s,%s,'compra_directa',"
                    "'confirmada')", (id_vendedor, emp, kw.get("cantidad", 2), kw.get("precio", 50.0),
                                      kw.get("divisa", "EUR")))
        txid = cur.lastrowid
        conn.commit()
        return txid


def test_ciclo_feliz_escrow(db, fab):
    emp = fab.empresa("EMP escrow feliz")
    vendedor = 8801
    fab.al_limpiar(lambda: _limpia(db, emp, [tx], vendedor))
    # Vendedor con cobros conectados y verificados (cross-tenant → id_empresa plataforma).
    CU.registrar_token("vendedor", vendedor, "acct_v1", status="verified", payouts_enabled=True,
                       charges_enabled=True, id_empresa=PLATAFORMA)
    tx = _nuevo_tx(db, emp, vendedor, cantidad=2, precio=50.0)   # importe 100

    r = ESC.iniciar_retencion(tx, comision_pct=10)
    assert r["ok"] and r["estado_pago"] == "FUNDS_HELD"
    assert r["comision"] == 10.0 and r["payment_ref"].startswith("pi_sim_")
    # Idempotencia: repetir no recobra.
    r2 = ESC.iniciar_retencion(tx, comision_pct=10)
    assert r2["idempotente"] is True and r2["estado_pago"] == "FUNDS_HELD"

    assert ESC.marcar_en_preparacion(tx)["estado_pago"] == "IN_FULFILLMENT"
    # Confirmar entrega libera automáticamente.
    fin = ESC.confirmar_entrega(tx)
    assert fin["ok"] and fin["estado_pago"] == "FUNDS_RELEASED" and fin["transfer_ref"]
    assert ESC.estado(tx) == "FUNDS_RELEASED"
    # Liberar de nuevo es idempotente.
    assert ESC.liberar(tx)["idempotente"] is True


def test_disputa_y_reembolso(db, fab):
    emp = fab.empresa("EMP escrow disputa")
    vendedor = 8802
    fab.al_limpiar(lambda: _limpia(db, emp, [tx], vendedor))
    CU.registrar_token("vendedor", vendedor, "acct_v2", status="verified", payouts_enabled=True,
                       id_empresa=PLATAFORMA)
    tx = _nuevo_tx(db, emp, vendedor, cantidad=1, precio=200.0)

    assert ESC.iniciar_retencion(tx, comision_pct=0)["estado_pago"] == "FUNDS_HELD"
    assert ESC.abrir_disputa(tx, motivo="mercancía dañada")["estado_pago"] == "IN_DISPUTE"
    # Desde disputa se puede reembolsar.
    r = ESC.reembolsar(tx)
    assert r["ok"] and r["estado_pago"] == "REFUNDED" and r["refund_ref"]
    # No se puede liberar tras reembolso.
    assert ESC.liberar(tx)["ok"] is False


def test_guard_vendedor_sin_cobros(db, fab):
    emp = fab.empresa("EMP escrow guard")
    vendedor = 8803   # sin cuenta conectada
    fab.al_limpiar(lambda: _limpia(db, emp, [tx], vendedor))
    tx = _nuevo_tx(db, emp, vendedor)
    r = ESC.iniciar_retencion(tx, comision_pct=5)
    assert r["ok"] is False and r["error"] == "vendedor_sin_cobros_conectados"
