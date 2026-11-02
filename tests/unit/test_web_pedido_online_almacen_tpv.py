"""
Tests · Encargo a almacén — Parte D (rediseño): la construcción del pedido (búsqueda de artículo,
almacenes por proximidad, cliente) se movió al Portal del Empleado (`src/backend/portal_empleado_web`,
ruta `/encargo`); `_VentaOnlineDialog` en el TPV se redujo a un selector de encargos `PENDIENTE`
ya construidos, que carga sus líneas a la cesta (`agregar_lineas_externas`) para cobrarlos.

  1. `_VentaOnlineDialog._buscar()` lista los pedidos PENDIENTE de la tienda activa.
  2. `_VentaOnlineDialog._cargar_seleccionado()` vuelca las líneas del pedido elegido a la cesta del
     TPV y cuelga SOLO `{"id_pedido": ...}` de `TPVWindow._encargo_pendiente` (ya no cliente/líneas/
     almacén: el pedido ya existe).
  3. `id_almacen` por línea se sigue persistiendo igual (`crear_pedido_online`, sin cambios de
     comportamiento por defecto — el `contexto` explícito añadido para el portal es opcional).
  4. Volcado a la CESTA del TPV: `TPVWindow.agregar_lineas_externas` APÉNDA (no reemplaza) y fusiona
     por código, en cualquier momento de la compra (sin cambios).
"""

import os
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_selector_lista_pedidos_pendientes_de_la_tienda():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.db import stock_almacen as SA
    from src.db.empresa import empresa_actual_id
    from src.services.tpv import online_orders_service as OS
    SA.ensure_almacenes_empresa()
    central = SA.almacen_central()
    assert central is not None
    cod = "PWT-" + uuid.uuid4().hex[:6].upper()
    SA.incrementar_stock(cod, central, 7)

    ref = "Cliente-" + uuid.uuid4().hex[:6]
    pid = OS.crear_encargo_almacen(
        {"nombre": ref},
        [{"codigo": cod, "nombre": "Test", "cantidad": 3, "precio": 2.0, "id_almacen": central}])
    assert pid

    from src.gui.tpv import _VentaOnlineDialog
    d = _VentaOnlineDialog(empleado="E", id_caja="C")
    d.inp_buscar.setText(ref)
    d._buscar()
    # El pedido recién creado (PENDIENTE) aparece en la lista, buscándolo por nombre de cliente.
    assert any(p.get("id_pedido") == pid for p in d._pedidos)
    # La tabla refleja la referencia corta (8 primeros caracteres del id_pedido, mismo recorte que
    # usa el resto de la app: `pagina_pedidos`/portal, `_crear_encargo_tras_venta`).
    textos_col0 = [d.tabla.item(r, 0).text() for r in range(d.tabla.rowCount())]
    assert pid[:8] in textos_col0


def test_cargar_seleccionado_vuelca_cesta_y_guarda_solo_id_pedido(monkeypatch):
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    # `_cargar_seleccionado()` termina mostrando un aviso de éxito vía
    # `assets.estilo_global.mostrar_mensaje` (modal `.exec()`) — en headless (offscreen, sin usuario
    # que lo cierre) eso bloquearía el test para siempre. Mismo patrón ya usado en el resto de la
    # suite (p.ej. `test_migracion_gui.py`, `test_recetas_gui.py`): neutralizarlo con monkeypatch.
    import assets.estilo_global as EG
    monkeypatch.setattr(EG, "mostrar_mensaje", lambda *a, **k: None)
    from src.db import stock_almacen as SA
    from src.services.tpv import online_orders_service as OS
    SA.ensure_almacenes_empresa()
    central = SA.almacen_central()
    cod = "PWY-" + uuid.uuid4().hex[:6].upper()
    ref = "Cliente-" + uuid.uuid4().hex[:6]
    pid = OS.crear_encargo_almacen(
        {"nombre": ref},
        [{"codigo": cod, "nombre": "Test Y", "cantidad": 2, "precio": 5.0, "id_almacen": central}])
    assert pid

    from src.gui.tpv import _VentaOnlineDialog, TPVWindow

    class _TPVFake:
        """Doble mínimo de TPVWindow: solo lo que `_cargar_seleccionado`/`_tpv_window` usan."""
        def __init__(self):
            self.llamadas = []
            self._encargo_pendiente = None

        def agregar_lineas_externas(self, lineas):
            self.llamadas.append(lineas)

    tpv_fake = _TPVFake()
    d = _VentaOnlineDialog(empleado="E", id_caja="C")
    # `_tpv_window` sube por la cadena de padres buscando una instancia REAL de TPVWindow; en este
    # test unitario (sin levantar todo el TPV) se sustituye directamente por el doble.
    d._tpv_window = lambda: tpv_fake
    d.inp_buscar.setText(ref)
    d._buscar()
    assert d._pedidos and d._pedidos[0]["id_pedido"] == pid
    d.tabla.selectRow(0)
    d._cargar_seleccionado()

    assert tpv_fake._encargo_pendiente == {"id_pedido": pid}
    assert len(tpv_fake.llamadas) == 1
    lineas = tpv_fake.llamadas[0]
    assert len(lineas) == 1
    assert lineas[0]["codigo"] == cod and lineas[0]["cantidad"] == 2 and lineas[0]["precio"] == 5.0


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


def test_crear_pedido_online_con_contexto_explicito_no_usa_ctx():
    """El `contexto` opcional (añadido para el Portal del Empleado, que corre sin sesión de
    escritorio) debe fijar id_empresa/id_tienda/id_usuario/trabajador directamente, sin llamar a
    `_ctx()` — y sin alterar el comportamiento por defecto (sin `contexto`) de ningún otro
    llamador (GUI de escritorio, adaptadores de marketplace)."""
    from src.db import stock_almacen as SA
    from src.db.conexion import obtener_conexion
    from src.db.empresa import empresa_actual_id
    from src.services.tpv import online_orders_service as OS
    SA.ensure_almacenes_empresa()
    central = SA.almacen_central()
    emp = empresa_actual_id()
    pid = OS.crear_pedido_online(
        {"nombre": "Cli Contexto"},
        [{"codigo": "PWZ", "nombre": "Z", "cantidad": 1, "precio": 9.0, "id_almacen": central}],
        contexto={"id_empresa": emp, "id_tienda": 999999, "id_usuario": 4242,
                 "trabajador": "Empleado Portal"})
    assert pid
    with obtener_conexion() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id_empresa, id_tienda, id_usuario, trabajador FROM pedidos_online "
            "WHERE id_pedido=%s", (pid,))
        row = cur.fetchone()
    assert row is not None
    id_empresa, id_tienda, id_usuario, trabajador = row if not isinstance(row, dict) else (
        row["id_empresa"], row["id_tienda"], row["id_usuario"], row["trabajador"])
    assert id_empresa == emp and int(id_tienda) == 999999
    assert int(id_usuario) == 4242 and trabajador == "Empleado Portal"


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
