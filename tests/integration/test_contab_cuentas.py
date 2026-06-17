"""E6.1 · Plan contable: activación (seed PGC), cuentas (CRUD), ejercicios."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_activar_clona_plan_y_abre_ejercicio(db, fab):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CONTA ACT")
    fab.al_limpiar(lambda: _borra(db, emp))
    assert K.activar(emp, anio=2026)
    assert K.contabilidad_activa(emp)
    cuentas = K.listar_cuentas(emp)
    cods = {c["codigo"] for c in cuentas}
    assert {"700", "477", "600", "472", "430", "400", "570"} <= cods
    # tipo/naturaleza correctos.
    c700 = K.obtener_cuenta("700", emp)
    assert c700["tipo"] == "ingreso" and c700["naturaleza"] == "acreedora" and c700["grupo"] == 7
    # ejercicio abierto.
    ej = K.obtener_ejercicio(2026, emp)
    assert ej and ej["estado"] == "abierto" and not K.ejercicio_cerrado(2026, emp)
    assert K.obtener_config(emp)["ejercicio_actual"] == 2026


def test_activar_es_idempotente(db, fab):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CONTA IDEMP")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, 2026); n1 = len(K.listar_cuentas(emp))
    K.activar(emp, 2026); n2 = len(K.listar_cuentas(emp))
    assert n1 == n2 and n1 > 0          # no duplica el plan


def test_crud_cuenta_y_filtros(db, fab):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CONTA CTA")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, 2026)
    assert K.crear_cuenta("4300001", "Cliente Demo SL", "activo", "deudora", id_empresa=emp)
    assert K.obtener_cuenta("4300001", emp)["nombre"] == "Cliente Demo SL"
    assert K.actualizar_cuenta("4300001", id_empresa=emp, nombre="Cliente Demo 2")
    assert K.obtener_cuenta("4300001", emp)["nombre"] == "Cliente Demo 2"
    assert any(c["codigo"] == "700" for c in K.listar_cuentas(emp, grupo=7))
    assert all(c["grupo"] == 7 for c in K.listar_cuentas(emp, grupo=7))


def test_aislamiento_por_empresa(db, fab):
    from src.services.contabilidad import cuentas as K
    a = fab.empresa("CONTA A"); b = fab.empresa("CONTA B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    K.activar(a, 2026)
    assert K.listar_cuentas(b) == [] and not K.contabilidad_activa(b)
    assert K.obtener_cuenta("700", b) is None
