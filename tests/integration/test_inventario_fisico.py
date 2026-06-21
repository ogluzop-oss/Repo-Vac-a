"""
INV.2 · Inventario físico / recuento auditado.

Ciclo de vida (crear/abrir/cerrar/anular), recuento + diferencias, ajuste auditado al
cierre con registro AJUSTE en kárdex (INV.1), trazabilidad, validaciones, informes,
multiempresa y GUI.
"""

import pytest

pytestmark = pytest.mark.db

from src.db import inventario_fisico as INV, kardex
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant


def _limpia(db, cod=None, emp=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        if cod:
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
        if emp and emp != EMPRESA_DEFAULT_ID:
            cur.execute("DELETE FROM inventarios WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _stock(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0) FROM articulos "
                    "WHERE codigo=%s", (cod,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def _inv(db, emp=EMPRESA_DEFAULT_ID, nombre="Inv test"):
    iid = INV.crear_inventario(nombre, id_empresa=emp, id_tienda=None, usuario="ana")
    fab_borra = lambda: _borra_inv(db, iid)
    return iid, fab_borra


def _borra_inv(db, iid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM inventarios WHERE id=%s", (iid,))
        conn.commit()


# ── Ciclo de vida ─────────────────────────────────────────────────────────────
def test_ciclo_vida(db, fab):
    iid, borra = _inv(db); fab.al_limpiar(borra)
    assert INV.obtener_inventario(iid)["estado"] == INV.BORRADOR
    assert INV.abrir_inventario(iid)
    assert INV.obtener_inventario(iid)["estado"] == INV.ABIERTO
    assert INV.obtener_inventario(iid)["fecha_apertura"] is not None


def test_anular(db, fab):
    iid, borra = _inv(db); fab.al_limpiar(borra)
    assert INV.anular_inventario(iid)
    assert INV.obtener_inventario(iid)["estado"] == INV.ANULADO
    with pytest.raises(INV.InventarioError):           # cerrado/anulado no transita
        INV.abrir_inventario(iid)


def test_no_cerrar_si_no_abierto(db, fab):
    iid, borra = _inv(db); fab.al_limpiar(borra)
    with pytest.raises(INV.InventarioError, match="ABIERTO"):
        INV.cerrar_inventario(iid)


# ── Recuento + diferencias ───────────────────────────────────────────────────
def test_recuento_calcula_diferencia(db, fab):
    cod = fab.articulo(stock_total=80, stock_tienda=20)      # esperado 100
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    assert INV.registrar_recuento(iid, cod, 95)
    ln = INV.listar_lineas(iid)[0]
    assert ln["stock_esperado"] == 100 and ln["stock_contado"] == 95 and ln["diferencia"] == -5


def test_recuento_rechaza_articulo_inexistente(db, fab):
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    with pytest.raises(INV.InventarioError, match="inexistente"):
        INV.registrar_recuento(iid, "NO_EXISTE_XYZ", 5)


def test_cerrado_no_editable(db, fab):
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    INV.registrar_recuento(iid, cod, 10)
    INV.cerrar_inventario(iid, usuario="ana")
    with pytest.raises(INV.InventarioError, match="no editable"):
        INV.registrar_recuento(iid, cod, 8)


# ── Ajuste auditado + kárdex + trazabilidad ──────────────────────────────────
def test_cierre_aplica_ajuste_y_kardex(db, fab):
    cod = fab.articulo(stock_total=80, stock_tienda=20)      # esperado 100
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    INV.registrar_recuento(iid, cod, 95)
    res = INV.cerrar_inventario(iid, usuario="ana")
    assert res["ajustes_aplicados"] == 1
    assert _stock(db, cod) == 95                              # stock real ajustado
    mv = kardex.listar_movimientos(codigo=cod, tipo="AJUSTE")
    assert len(mv) == 1
    m = mv[0]
    assert m["stock_anterior"] == 100 and m["stock_nuevo"] == 95 and m["cantidad"] == -5
    assert m["id_documento"] == f"INV-{iid}" and m["origen"] == "INVENTARIO"
    assert m["usuario"] == "ana"                              # trazabilidad


def test_sin_diferencia_no_ajusta(db, fab):
    cod = fab.articulo(stock_total=30, stock_tienda=0)
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    INV.registrar_recuento(iid, cod, 30)                     # sin diferencia
    res = INV.cerrar_inventario(iid, usuario="ana")
    assert res["ajustes_aplicados"] == 0
    assert kardex.listar_movimientos(codigo=cod, tipo="AJUSTE") == []


# ── Informes ─────────────────────────────────────────────────────────────────
def test_informes(db, fab):
    cod = fab.articulo(stock_total=50)
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    INV.registrar_recuento(iid, cod, 45)
    assert len(INV.diferencias_por_inventario(iid)) == 1
    assert any(i["id"] == iid for i in INV.inventarios_abiertos())
    INV.cerrar_inventario(iid, usuario="ana")
    assert any(i["id"] == iid for i in INV.inventarios_cerrados())
    assert len(INV.diferencias_por_articulo(cod)) >= 1


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_multiempresa(db, fab):
    emp2 = fab.empresa("INV2 B")
    fab.al_limpiar(lambda: _limpia(db, emp=emp2))
    iid1, b1 = _inv(db, EMPRESA_DEFAULT_ID); fab.al_limpiar(b1)
    iid2 = INV.crear_inventario("B", id_empresa=emp2, usuario="x")
    # no visible desde la otra empresa
    assert INV.obtener_inventario(iid1, emp2) is None
    assert INV.obtener_inventario(iid2, EMPRESA_DEFAULT_ID) is None
    assert all(i["id"] != iid2 for i in INV.listar_inventarios(EMPRESA_DEFAULT_ID))
    # no se puede cerrar un inventario de otra empresa desde emp2
    with pytest.raises(INV.InventarioError):
        INV.cerrar_inventario(iid1, id_empresa=emp2)


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_gui(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    cod = fab.articulo(stock_total=40)
    fab.al_limpiar(lambda: _limpia(db, cod))
    iid, borra = _inv(db, nombre="GUI inv"); fab.al_limpiar(borra)
    INV.abrir_inventario(iid)
    INV.registrar_recuento(iid, cod, 38)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        from src.gui.inventario_fisico import InventarioFisicoWindow
        w = InventarioFisicoWindow(usuario={"nombre": "ana", "perfil": "GERENTE"})
        i = w.cmb_inv.findData(iid)
        assert i >= 0
        w.cmb_inv.setCurrentIndex(i)
        assert w.tabla.rowCount() == 1
        w.close()
