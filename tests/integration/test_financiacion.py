"""Financiacion — cuadro de amortizacion frances, prestamos/leasing, vencimientos, deuda viva."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def limpia(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM financiacion_cuotas WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM financiaciones WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM vencimientos WHERE id_empresa=%s AND origen='financiacion'", (E,))
        conn.commit()


def test_cuadro_amortizacion(db, limpia):
    from src.services.finanzas import financiacion as F
    cuadro = F.cuadro_amortizacion(12000, 6.0, 12, periodicidad="mensual")
    assert len(cuadro) == 12
    assert cuadro[-1]["saldo_vivo"] == 0.0                  # se amortiza por completo
    assert cuadro[0]["interes"] > cuadro[-1]["interes"]     # interes decreciente
    # principal + interes ~ cuota
    assert abs(cuadro[0]["principal"] + cuadro[0]["interes"] - cuadro[0]["cuota"]) < 0.02


def test_prestamo_genera_vencimientos(db, limpia):
    from src.services.finanzas import financiacion as F
    fid = F.crear_financiacion("prestamo", 6000, 5.0, 6, id_empresa=E)
    assert fid and len(F.cuadro(fid)) == 6
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vencimientos WHERE id_empresa=%s AND origen='financiacion'", (E,))
        n = cur.fetchone()
        n = n[0] if not isinstance(n, dict) else list(n.values())[0]
    assert n == 6


def test_pago_cuota_y_deuda_viva(db, limpia):
    from src.services.finanzas import financiacion as F
    fid = F.crear_financiacion("leasing", 10000, 4.0, 10, valor_residual=1000, id_empresa=E)
    d0 = F.deuda_viva(id_empresa=E)["total"]
    assert d0 >= 10000
    r = F.registrar_pago_cuota(fid, 1, id_empresa=E)
    assert r["ok"] and F.deuda_viva(id_empresa=E)["total"] < d0
    with pytest.raises(ValueError):
        F.crear_financiacion("zzz", 100, 1, 1, id_empresa=E)
