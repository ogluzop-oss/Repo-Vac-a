"""
Tests · Nuevo pedido online (Portal Web) — Fase WEB-13:
  1. Multi-artículo: el diálogo mantiene varias líneas.
  2. Selección de ALMACÉN por artículo alimentada del stock FÍSICO por almacén (Kárdex / stock_almacen):
     solo aparecen almacenes con existencias; la línea guarda el almacén elegido.
  3. Volcado a la CESTA del TPV: `TPVWindow.agregar_lineas_externas` APÉNDA (no reemplaza) y fusiona por
     código, en cualquier momento de la compra.
"""

import os
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_selector_almacen_desde_stock_fisico():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.db import stock_almacen as SA
    cod = "PWT-" + uuid.uuid4().hex[:6].upper()
    SA.ensure_almacenes_empresa()
    central = SA.almacen_central()
    assert central is not None
    SA.incrementar_stock(cod, central, 7)   # stock físico real en el almacén central

    from src.gui.tpv import _VentaOnlineDialog
    d = _VentaOnlineDialog(empleado="E", id_caja="C")
    d._poblar_almacenes(cod)
    # El combo lista SOLO almacenes con stock (aquí, Central con 7 ud.) y expone el id del almacén.
    datas = [d.cmb_almacen.itemData(i) for i in range(d.cmb_almacen.count())]
    textos = [d.cmb_almacen.itemText(i) for i in range(d.cmb_almacen.count())]
    assert central in datas
    assert any("7" in t for t in textos)

    # Al añadir la línea, se guarda el almacén elegido (multi-artículo ya soportado por _lineas).
    d._art = {"codigo": cod, "nombre": "Test", "precio": 2.0}
    d.inp_cant.setText("3")
    d._add_linea()
    assert len(d._lineas) == 1
    assert d._lineas[0]["id_almacen"] == central and d._lineas[0]["cantidad"] == 3
    assert d.tabla.columnCount() == 6   # incluye la columna Almacén


def test_pedido_persiste_id_almacen_por_linea():
    from src.db import stock_almacen as SA
    from src.db.conexion import obtener_conexion
    from src.services.tpv import online_orders_service as OS
    SA.ensure_almacenes_empresa()
    central = SA.almacen_central()
    pid = OS.crear_pedido_online(
        {"nombre": "Cli"},
        [{"codigo": "PWX", "nombre": "X", "cantidad": 2, "precio": 3.0, "id_almacen": central}])
    assert pid
    with obtener_conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT id_almacen FROM pedidos_online_items WHERE id_pedido=%s", (pid,))
        row = cur.fetchone()
    assert row is not None and row[0] == central   # el almacén de origen queda registrado


def test_volcado_a_cesta_tpv_apend_y_merge():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.tpv import TPVWindow
    assert hasattr(TPVWindow, "agregar_lineas_externas")

    # Cesta existente con un artículo (no se reemplaza; se apéndan/fusionan los del pedido online).
    class _CestaFake:
        def _refresh_tabla(self):
            pass
    _CestaFake.agregar_lineas_externas = TPVWindow.agregar_lineas_externas
    f = _CestaFake()
    f._lineas = [{"codigo": "X", "nombre": "X", "seccion": "S", "cantidad": 1,
                  "precio": 1.0, "descuento_pct": 0.0, "subtotal": 1.0, "iva": 21.0}]
    f.agregar_lineas_externas([
        {"codigo": "A1", "nombre": "A1", "cantidad": 2, "precio": 2.0},
        {"codigo": "X", "nombre": "X", "cantidad": 1, "precio": 1.0},   # ya en cesta → fusiona
    ])
    por_cod = {l["codigo"]: l["cantidad"] for l in f._lineas}
    assert por_cod == {"X": 2, "A1": 2} and len(f._lineas) == 2
    # Línea nueva con el formato del carrito del TPV.
    a1 = next(l for l in f._lineas if l["codigo"] == "A1")
    assert a1["seccion"] == "ONLINE" and a1["subtotal"] == 4.0 and "iva" in a1
