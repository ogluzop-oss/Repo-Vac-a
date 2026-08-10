"""
Pedir mercancía al almacén central (LOGÍSTICA). La tienda crea una solicitud; al servirla, el stock se mueve
central→tienda por el motor oficial (traspasar_stock → kárdex). Servicio total y parcial, y cancelación.
"""

import pytest

from src.db import stock_almacen as _alm
from src.services.logistica import solicitudes as S


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture
def setup(fab, emp, db):
    # Asegura almacenes (central + general + uno por tienda). Necesita al menos una tienda real.
    mapa = _alm.ensure_almacenes_empresa(emp)
    tiendas = mapa.get("tiendas") or {}
    if not tiendas:
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO tiendas (id_empresa, codigo_tienda) VALUES (%s,'TND-SC')", (emp,))
            c.commit()
        mapa = _alm.ensure_almacenes_empresa(emp)
        tiendas = mapa.get("tiendas") or {}
    tid = sorted(tiendas)[0]
    central, dest = mapa["central"], tiendas[tid]
    assert central and dest and central != dest
    with db.obtener_conexion() as c, c.cursor() as cur:
        for cod in ("SC-1", "SC-2"):
            cur.execute("INSERT INTO articulos (codigo,nombre,id_empresa) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre)", (cod, "Art " + cod, emp))
        c.commit()
    # deja el central con 100/3 y la tienda a 0 para asertar el movimiento
    _alm.ajustar_stock("SC-1", central, 100, id_empresa=emp)
    _alm.ajustar_stock("SC-2", central, 3, id_empresa=emp)
    _alm.ajustar_stock("SC-1", dest, 0, id_empresa=emp)
    _alm.ajustar_stock("SC-2", dest, 0, id_empresa=emp)

    def _limpiar():
        for sol in S.listar_solicitudes(id_empresa=emp, id_tienda=tid):
            fab._borrar("solicitudes_traspaso_items", "id_solicitud", sol["id"])
        fab._borrar("solicitudes_traspaso", "id_tienda", tid)
        for cod in ("SC-1", "SC-2"):
            fab._borrar("articulos", "codigo", cod)
            fab._borrar("stock_almacen", "codigo_articulo", cod)
            fab._borrar("movimientos_stock", "codigo_articulo", cod)
    fab.al_limpiar(_limpiar)
    return {"central": central, "dest": dest, "tid": tid}


def test_crear_solicitud(emp, setup):
    tid = setup["tid"]
    sid = S.crear_solicitud(tid, [{"codigo": "SC-1", "cantidad": 10}], id_empresa=emp)
    assert sid
    sol = S.obtener_solicitud(sid, id_empresa=emp)
    assert sol["estado"] == "PENDIENTE" and len(sol["items"]) == 1
    assert sol["items"][0]["codigo_articulo"] == "SC-1" and sol["items"][0]["cantidad_solicitada"] == 10


def test_servir_total_mueve_stock(emp, setup, db):
    central, dest, tid = setup["central"], setup["dest"], setup["tid"]
    sid = S.crear_solicitud(tid, [{"codigo": "SC-1", "cantidad": 10}], id_empresa=emp)
    res = S.servir_solicitud(sid, id_empresa=emp)
    assert res["ok"] and res["estado"] == "SERVIDA" and res["movidas"] == 10
    assert _alm.obtener_stock_almacen("SC-1", central, emp) == 90    # central baja
    assert _alm.obtener_stock_almacen("SC-1", dest, emp) == 10       # tienda sube
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE codigo_articulo='SC-1' AND "
                    "tipo_movimiento='TRASPASO'")
        assert cur.fetchone()[0] >= 1                                # kárdex TRASPASO


def test_servir_parcial_si_falta_stock(emp, setup):
    central, dest, tid = setup["central"], setup["dest"], setup["tid"]
    sid = S.crear_solicitud(tid, [{"codigo": "SC-2", "cantidad": 10}], id_empresa=emp)  # central solo tiene 3
    res = S.servir_solicitud(sid, id_empresa=emp)
    assert res["ok"] and res["estado"] == "PARCIAL" and res["movidas"] == 3
    assert _alm.obtener_stock_almacen("SC-2", central, emp) == 0
    assert _alm.obtener_stock_almacen("SC-2", dest, emp) == 3
    assert S.obtener_solicitud(sid, id_empresa=emp)["items"][0]["cantidad_servida"] == 3


def test_cancelar(emp, setup):
    tid = setup["tid"]
    sid = S.crear_solicitud(tid, [{"codigo": "SC-1", "cantidad": 5}], id_empresa=emp)
    assert S.cancelar_solicitud(sid, id_empresa=emp)
    assert S.obtener_solicitud(sid, id_empresa=emp)["estado"] == "CANCELADA"
    assert S.servir_solicitud(sid, id_empresa=emp)["ok"] is False    # cancelada no se sirve


def test_dialogo_pedido_central(emp, setup, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    import src.gui.pedido_central_gui as PC
    monkeypatch.setattr(PC, "mostrar_mensaje", lambda *a, **k: None)
    # fija la empresa de sesión = la del setup (otro test del full-run pudo cambiarla)
    monkeypatch.setattr("src.db.empresa.empresa_actual_id", lambda: emp)
    dlg = PC.PedidoCentralDialog(usuario={"nombre": "tester"})
    try:
        idx = dlg.cb_tienda.findData(setup["tid"])
        assert idx >= 0
        dlg.cb_tienda.setCurrentIndex(idx)
        dlg._add_item("SC-1", 5)                       # flujo: añadir línea → crear → servir
        dlg._crear()
        sid = dlg.ultima_sid                            # selecciona EXACTAMENTE la solicitud creada
        fila = next(i for i in range(dlg.lst.count())
                    if dlg.lst.item(i).data(Qt.ItemDataRole.UserRole) == sid)
        dlg.lst.setCurrentRow(fila)
        dlg._servir()                                  # el diálogo sirve vía el servicio (mueve stock por kárdex)
        assert S.obtener_solicitud(sid, id_empresa=emp)["estado"] == "SERVIDA"
        # (el movimiento de stock central→tienda está cubierto por test_servir_total_mueve_stock)
    finally:
        dlg.deleteLater()
