"""E6.6 · Libros de IVA (repercutido/soportado) + borrador modelo 303."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("contab_asientos", "contab_cola", "contab_cuentas",
                  "contab_ejercicios", "contab_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


@pytest.fixture
def libros(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("IVA 303")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    # Venta 121 (base 100, IVA 21) + compra 60.5 (base 50, IVA 10.5).
    Pg.encolar_venta("v1", 121.0, "2026-07-01", "efectivo", id_empresa=emp)
    Pg.encolar_compra("c1", 60.5, "2026-07-02", id_empresa=emp, base=50.0, iva=10.5)
    Pg.procesar_cola(emp)
    return emp


def test_libro_repercutido_y_soportado(libros):
    from src.services.contabilidad import iva as IVA
    rep = IVA.libro_iva("repercutido", id_empresa=libros, anio=2026)
    assert rep["total_cuota"] == 21.0 and rep["total_base"] == 100.0 and len(rep["lineas"]) == 1
    sop = IVA.libro_iva("soportado", id_empresa=libros, anio=2026)
    assert sop["total_cuota"] == 10.5 and sop["total_base"] == 50.0


def test_borrador_303(libros):
    from src.services.contabilidad import iva as IVA
    r = IVA.resumen_303(id_empresa=libros, anio=2026)
    assert r["iva_devengado_cuota"] == 21.0 and r["iva_deducible_cuota"] == 10.5
    assert r["resultado"] == 10.5 and r["sentido"] == "a ingresar"


def test_devolucion_resta_repercutido(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg, iva as IVA
    emp = fab.empresa("IVA DEVOL")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    Pg.encolar_venta("v1", 121.0, "2026-07-01", "efectivo", id_empresa=emp)
    Pg.encolar_devolucion("d1", 60.5, "2026-07-03", tipo="venta", forma_pago="efectivo", id_empresa=emp)
    Pg.procesar_cola(emp)
    rep = IVA.libro_iva("repercutido", id_empresa=emp, anio=2026)
    # 21 (venta) - 10.5 (devolución) = 10.5 neto repercutido.
    assert rep["total_cuota"] == 10.5
