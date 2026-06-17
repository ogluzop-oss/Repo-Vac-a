"""E6.2 · Asientos: cuadre, diario, numeración, inmutabilidad, contraasiento, auditoría."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp,))   # cascada apuntes
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _venta_simple():
    # Venta 121 € (base 100, IVA 21) cobrada en caja.
    return [{"codigo_cuenta": "570", "debe": 121.0},
            {"codigo_cuenta": "700", "haber": 100.0},
            {"codigo_cuenta": "477", "haber": 21.0}]


def test_crear_asiento_cuadrado(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS CUADRE")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    r = A.crear_asiento("2026-03-10", _venta_simple(), concepto="Venta TPV", id_empresa=emp)
    assert r and r["estado"] == "contabilizado" and r["numero"] == 1 and r["total"] == 121.0
    a = A.obtener_asiento(r["id"], emp)
    assert len(a["apuntes"]) == 3 and float(a["total_debe"]) == float(a["total_haber"]) == 121.0


def test_descuadre_rechazado(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS DESC")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    malo = [{"codigo_cuenta": "570", "debe": 121.0}, {"codigo_cuenta": "700", "haber": 100.0}]
    assert A.crear_asiento("2026-03-10", malo, id_empresa=emp) is None


def test_numeracion_correlativa(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS NUM")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    n = [A.crear_asiento("2026-03-10", _venta_simple(), id_empresa=emp)["numero"] for _ in range(3)]
    assert n == [1, 2, 3]
    assert [x["numero"] for x in A.listar_diario(emp, anio=2026)] == [1, 2, 3]


def test_contraasiento_y_inmutabilidad(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS ANUL")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    r = A.crear_asiento("2026-03-10", _venta_simple(), id_empresa=emp)
    contra = A.anular(r["id"], fecha="2026-03-11", id_empresa=emp)
    assert contra and contra["numero"] == 2
    orig = A.obtener_asiento(r["id"], emp)
    assert orig["estado"] == "anulado" and orig["anulado_por"] == contra["id"]
    # El contraasiento invierte debe/haber.
    ca = A.obtener_asiento(contra["id"], emp)
    ap570 = next(x for x in ca["apuntes"] if x["codigo_cuenta"] == "570")
    assert float(ap570["haber"]) == 121.0 and float(ap570["debe"]) == 0.0
    # Re-anular un ya anulado no procede.
    assert A.anular(r["id"], id_empresa=emp) is None


def test_bloqueo_por_ejercicio_cerrado(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS CIERRE")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE contab_ejercicios SET estado='cerrado' WHERE id_empresa=%s AND anio=2026", (emp,))
        conn.commit()
    assert A.crear_asiento("2026-03-10", _venta_simple(), id_empresa=emp) is None


def test_cadena_auditoria(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K
    emp = fab.empresa("AS AUDIT")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    for _ in range(3):
        A.crear_asiento("2026-03-10", _venta_simple(), id_empresa=emp)
    assert A.cadena_auditoria_valida(emp, anio=2026) is True
    # Manipular un total rompe la cadena.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE contab_asientos SET total_debe=999 WHERE id_empresa=%s AND numero=2", (emp,))
        conn.commit()
    assert A.cadena_auditoria_valida(emp, anio=2026) is False
