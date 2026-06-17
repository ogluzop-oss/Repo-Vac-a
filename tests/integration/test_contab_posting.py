"""E6.4 · Posting de ventas: cola, agregación diaria, factura, hook y mapeo."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp, cods=()):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_mapeo WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        for c in cods:
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (c,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _apuntes(emp, id_asiento):
    from src.services.contabilidad import asientos as A
    return {ap["codigo_cuenta"]: ap for ap in A.obtener_asiento(id_asiento, emp)["apuntes"]}


def test_agregacion_diaria_tickets(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg, informes as I
    emp = fab.empresa("POST DIA")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    Pg.encolar_venta("v1", 121.0, "2026-05-10", "efectivo", id_empresa=emp)
    Pg.encolar_venta("v2", 60.5, "2026-05-10", "tarjeta", id_empresa=emp)
    res = Pg.procesar_cola(emp)
    assert res["asientos"] == 1 and res["eventos"] == 2     # un solo asiento del día
    from src.services.contabilidad import asientos as A
    aid = A.listar_diario(emp, anio=2026)[0]["id"]
    ap = _apuntes(emp, aid)
    assert float(ap["570"]["debe"]) == 121.0 and float(ap["572"]["debe"]) == 60.5
    assert float(ap["700"]["haber"]) == 150.0 and float(ap["477"]["haber"]) == 31.5  # base/cuota de 181.5
    bal = I.balance_sumas_saldos(id_empresa=emp, anio=2026)
    assert bal["cuadra"]


def test_factura_venta_individual(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg, asientos as A
    emp = fab.empresa("POST FAC")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    Pg.encolar_venta("F1", 121.0, "2026-05-11", "factura", subtipo="factura", id_empresa=emp)
    assert Pg.procesar_cola(emp)["asientos"] == 1
    ap = _apuntes(emp, A.listar_diario(emp, anio=2026)[0]["id"])
    assert float(ap["430"]["debe"]) == 121.0 and float(ap["700"]["haber"]) == 100.0


def test_off_no_encola(db, fab):
    from src.services.contabilidad import posting as Pg
    emp = fab.empresa("POST OFF")
    fab.al_limpiar(lambda: _borra(db, emp))   # contabilidad NO activada
    assert Pg.encolar_venta("x", 100.0, "2026-05-10", id_empresa=emp) is None
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_cola WHERE id_empresa=%s", (emp,))
        assert cur.fetchone()[0] == 0


def test_idempotente(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("POST IDEMP")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    Pg.encolar_venta("v1", 121.0, "2026-05-10", "efectivo", id_empresa=emp)
    assert Pg.procesar_cola(emp)["asientos"] == 1
    assert Pg.procesar_cola(emp)["asientos"] == 0     # nada pendiente


def test_hook_venta_real_encola(db, fab):
    from src.db import conexion as cx
    from src.db.empresa import contexto_tenant
    from src.services.contabilidad import cuentas as K, posting as Pg, asientos as A
    emp = fab.empresa("POST HOOK")
    cod = fab.articulo(id_empresa=emp, precio=121.0, stock_tienda=10)
    fab.al_limpiar(lambda: _borra(db, emp, [cod])); K.activar(emp, 2026)
    with contexto_tenant(emp, None):
        vid = cx.registrar_venta_con_items([{"codigo": cod, "cantidad": 1, "precio_unitario": 121.0}])
        assert vid
        assert Pg.procesar_cola(emp)["asientos"] == 1
    assert A.listar_diario(emp)[0]["origen"] == "venta"


def test_mapeo_override(db, fab):
    from src.services.contabilidad import cuentas as K, mapeo as M, posting as Pg, asientos as A
    emp = fab.empresa("POST MAP")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    M.set_mapeo("venta", "705", id_empresa=emp)     # ventas → prestaciones de servicios
    Pg.encolar_venta("v1", 121.0, "2026-05-10", "efectivo", id_empresa=emp)
    Pg.procesar_cola(emp)
    ap = _apuntes(emp, A.listar_diario(emp, anio=2026)[0]["id"])
    assert "705" in ap and "700" not in ap
