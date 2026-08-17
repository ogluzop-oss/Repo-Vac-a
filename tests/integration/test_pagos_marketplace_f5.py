"""Marketplace + Pagos (F5) — cableado del escrow a la Lonja + orquestación para la GUI. `db`.

Cubre: una compra directa en la Lonja arranca el escrow automáticamente cuando el vendedor tiene cobros
conectados (FUNDS_HELD); la capa `operaciones` lista transacciones, confirma recepción (→FUNDS_RELEASED) y
expone el ledger. Sin cobros conectados, la compra sigue funcionando (queda sin escrow) — no rompe la Lonja.
"""

import pytest

from src.services import lonja
from src.services.pagos_marketplace import cuentas as CU, operaciones as OP

pytestmark = pytest.mark.db

PLATAFORMA = "00000000-0000-0000-0000-000000000001"


def _limpia(db, emp, id_vendedor):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM lonja_transacciones WHERE id_empresa=%s", (emp,))
        ids = [r[0] if not isinstance(r, dict) else r["id"] for r in cur.fetchall()]
        for t in ids:
            cur.execute("DELETE FROM pagos_eventos WHERE id_transaccion=%s", (t,))
        cur.execute("DELETE FROM lonja_transacciones WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (id_vendedor,))
        cur.execute("DELETE FROM psp_cuentas_conectadas WHERE tipo_parte='vendedor' AND id_parte=%s",
                    (id_vendedor,))
        cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (id_vendedor,))
        conn.commit()


def test_compra_directa_arranca_escrow_y_operaciones(db, fab):
    emp = fab.empresa("EMP f5 escrow")
    ven = lonja.alta_vendedor("Vend F5", divisa="EUR")
    vid = ven["id"]
    fab.al_limpiar(lambda: _limpia(db, emp, vid))
    # Vendedor con cobros conectados y verificados.
    CU.registrar_token("vendedor", vid, "acct_f5", status="verified", payouts_enabled=True,
                       id_empresa=PLATAFORMA)
    lid = lonja.publicar(vid, "ARTF5", 40.0, cantidad=5, permite_puja=False)

    r = lonja.comprar_directo(lid, emp, 2)          # importe 80
    assert r["ok"]
    tx = r["id_transaccion"]

    # El escrow arrancó automáticamente al comprar.
    filas = {f["id"]: f for f in OP.transacciones(emp)}
    assert tx in filas and filas[tx]["estado_pago"] == "FUNDS_HELD"
    assert filas[tx]["importe"] == 80.0

    # La GUI confirma la recepción → libera.
    assert OP.confirmar_recepcion(tx)["estado_pago"] == "FUNDS_RELEASED"
    tipos = [e["tipo"] for e in OP.ledger(tx)]
    assert "FUNDS_HELD" in tipos and "FUNDS_RELEASED" in tipos


def test_compra_sin_cobros_conectados_no_rompe(db, fab):
    emp = fab.empresa("EMP f5 sin cobros")
    ven = lonja.alta_vendedor("Vend F5b", divisa="EUR")
    vid = ven["id"]
    fab.al_limpiar(lambda: _limpia(db, emp, vid))
    lid = lonja.publicar(vid, "ARTF5B", 10.0, cantidad=3, permite_puja=False)

    r = lonja.comprar_directo(lid, emp, 1)          # el vendedor NO tiene cobros conectados
    assert r["ok"]                                   # la compra funciona igualmente
    filas = {f["id"]: f for f in OP.transacciones(emp)}
    assert filas[r["id_transaccion"]]["estado_pago"] in (None, "—")   # sin escrow (legacy)
