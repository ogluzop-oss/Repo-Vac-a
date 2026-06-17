"""E6.5 · Posting de compras y devoluciones → asientos."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("contab_asientos", "contab_cola", "contab_mapeo", "contab_cuentas",
                  "contab_ejercicios", "contab_config", "compras_facturas", "proveedores"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _apuntes(emp, aid):
    from src.services.contabilidad import asientos as A
    return {ap["codigo_cuenta"]: ap for ap in A.obtener_asiento(aid, emp)["apuntes"]}


def test_factura_compra_genera_asiento(db, fab):
    from src.db import compras as C, proveedores as P
    from src.db.empresa import contexto_tenant
    from src.services.contabilidad import asientos as A, cuentas as K, posting as Pg
    emp = fab.empresa("CCOMPRA")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    with contexto_tenant(emp, None):
        prov = P.crear_proveedor("PROV CONTAB", id_empresa=emp)
        # Factura: base 50, IVA 10.5, total 60.5 → encola al registrar.
        C.registrar_factura(id_proveedor=prov, numero_factura="FC-1", base=50.0, iva=10.5,
                            fecha_factura="2026-06-01", id_empresa=emp)
        assert Pg.procesar_cola(emp)["asientos"] == 1
    ap = _apuntes(emp, A.listar_diario(emp, anio=2026)[0]["id"])
    assert float(ap["600"]["debe"]) == 50.0 and float(ap["472"]["debe"]) == 10.5
    assert float(ap["400"]["haber"]) == 60.5


def test_devolucion_venta_genera_contraflujo(db, fab):
    from src.services.contabilidad import asientos as A, cuentas as K, posting as Pg
    emp = fab.empresa("CDEVOL")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    # Devolución de venta de 121 (base 100 + IVA 21) reembolsada en efectivo.
    Pg.encolar_devolucion("D1", 121.0, "2026-06-02", tipo="venta", forma_pago="efectivo", id_empresa=emp)
    assert Pg.procesar_cola(emp)["asientos"] == 1
    ap = _apuntes(emp, A.listar_diario(emp, anio=2026)[0]["id"])
    # 708 Devoluciones de ventas (Debe base) + 477 (Debe cuota) / 570 (Haber total)
    assert float(ap["708"]["debe"]) == 100.0 and float(ap["477"]["debe"]) == 21.0
    assert float(ap["570"]["haber"]) == 121.0


def test_balance_cuadra_con_ventas_y_compras(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg, informes as I
    emp = fab.empresa("CMIX")
    fab.al_limpiar(lambda: _borra(db, emp)); K.activar(emp, 2026)
    Pg.encolar_venta("v1", 121.0, "2026-06-01", "efectivo", id_empresa=emp)
    Pg.encolar_compra("c1", 60.5, "2026-06-01", id_empresa=emp, base=50.0, iva=10.5)
    Pg.procesar_cola(emp)
    assert I.balance_sumas_saldos(id_empresa=emp, anio=2026)["cuadra"]
