"""E6.3 · Mayor, balance de sumas y saldos, situación y PyG."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


@pytest.fixture
def libro(db, fab):
    """Una venta (121) y una compra (60.5) contabilizadas."""
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("CONTA INF")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    # Venta: 570 D121 / 700 H100 / 477 H21
    A.crear_asiento("2026-04-01", [{"codigo_cuenta": "570", "debe": 121.0},
                                   {"codigo_cuenta": "700", "haber": 100.0},
                                   {"codigo_cuenta": "477", "haber": 21.0}], id_empresa=emp)
    # Compra: 600 D50 / 472 D10.5 / 400 H60.5
    A.crear_asiento("2026-04-02", [{"codigo_cuenta": "600", "debe": 50.0},
                                   {"codigo_cuenta": "472", "debe": 10.5},
                                   {"codigo_cuenta": "400", "haber": 60.5}], id_empresa=emp)
    return emp


def test_mayor_saldo_acumulado(libro):
    from src.services.contabilidad import informes as I
    m = I.mayor("570", id_empresa=libro, anio=2026)
    assert m["total_debe"] == 121.0 and m["saldo"] == 121.0 and len(m["apuntes"]) == 1
    assert m["apuntes"][0]["saldo"] == 121.0


def test_balance_sumas_saldos_cuadra(libro):
    from src.services.contabilidad import informes as I
    b = I.balance_sumas_saldos(id_empresa=libro, anio=2026)
    assert b["cuadra"] and b["total_debe"] == b["total_haber"] == 181.5
    saldos = {c["codigo"]: c["saldo"] for c in b["cuentas"]}
    assert saldos["700"] == -100.0 and saldos["570"] == 121.0 and saldos["400"] == -60.5


def test_pyg_y_situacion(libro):
    from src.services.contabilidad import informes as I
    pyg = I.perdidas_ganancias(id_empresa=libro, anio=2026)
    assert pyg["ingresos"] == 100.0 and pyg["gastos"] == 50.0 and pyg["resultado"] == 50.0
    bs = I.balance_situacion(id_empresa=libro, anio=2026)
    # Activo: 570(121)+472(10.5)=131.5 ; Pasivo: 477(21)+400(60.5)=81.5 ; PN: resultado 50
    assert bs["activo"] == 131.5 and bs["pasivo"] == 81.5 and bs["patrimonio_neto"] == 50.0
    assert bs["cuadra"] is True
