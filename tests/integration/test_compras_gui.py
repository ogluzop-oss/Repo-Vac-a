"""E2-GUI · Ventana de Compras: apertura, navegación, CRUD y flujo completo."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp, cods=()):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        for c in cods:
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (c,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_ventana_abre_y_tiene_5_secciones(db, fab):
    from src.db.empresa import contexto_tenant
    from src.gui.compras_gestion import ComprasWindow
    emp = fab.empresa("GUI ABRE")
    fab.al_limpiar(lambda: _borra(db, emp))
    with contexto_tenant(emp, None):
        w = ComprasWindow(callback_vuelta=lambda: None, usuario={"nombre": "Tester"})
        assert w.stack.count() == 5
        # Navegación por todas las secciones.
        for i in range(5):
            w._ir(i)
            assert w.stack.currentIndex() == i
        w.close()


def test_crud_proveedor_desde_gui(db, fab):
    from src.db import proveedores as P
    from src.db.empresa import contexto_tenant
    from src.gui.compras_gestion import ComprasWindow
    emp = fab.empresa("GUI CRUD")
    fab.al_limpiar(lambda: _borra(db, emp))
    with contexto_tenant(emp, None):
        w = ComprasWindow(usuario={"nombre": "T"})
        w.in_prov_razon.setText("PROVEEDOR GUI SL")
        w.in_prov_cif.setText("B99999999")
        w.in_prov_email.setText("c@gui.test")
        assert w._guardar_proveedor() is True
        provs = P.listar_proveedores(id_empresa=emp)
        assert any(p["razon_social"] == "PROVEEDOR GUI SL" for p in provs)
        w._load_proveedores()
        assert w.tbl_prov.rowCount() >= 1
        w.close()


def test_flujo_completo_proveedor_pedido_recepcion_factura(db, fab):
    from src.db import compras as C
    from src.db.empresa import contexto_tenant
    from src.gui.compras_gestion import ComprasWindow
    emp = fab.empresa("GUI FLUJO")
    cod = fab.articulo(id_empresa=emp, stock_total=0)
    fab.al_limpiar(lambda: _borra(db, emp, [cod]))
    with contexto_tenant(emp, None):
        w = ComprasWindow(usuario={"nombre": "T"})
        # 1) Proveedor (vía GUI).
        w.in_prov_razon.setText("FLUJO PROV"); w._guardar_proveedor()
        from src.db import proveedores as P
        prov = P.listar_proveedores(id_empresa=emp)[0]["id_proveedor"]
        # 2) Pedido (vía método de la ventana).
        pid = w.crear_pedido(prov, [{"codigo": cod, "cantidad": 8, "precio_unitario": 1.5}])
        assert pid and C.obtener_pedido(pid, emp)["estado"] == "BORRADOR"
        # 3) Enviar + recibir todo (vía ventana) → stock actualizado.
        assert C.enviar_pedido(pid, emp)
        res = w.recibir_pedido(pid)
        assert res and res["estado_pedido"] == "RECIBIDO"
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT Stock_total FROM articulos WHERE codigo=%s", (cod,))
            assert cur.fetchone()[0] == 8
        # 4) Factura (vía ventana) vinculada al pedido + validación.
        fid = w.registrar_factura(prov, "F-GUI-1", base=12.0, iva=0.0, id_pedido=pid)
        assert fid
        r = C.validar_factura(fid, id_empresa=emp)
        assert r["estado"] == "validada"        # 8*1.5 = 12.0 == total pedido
        w.close()


def test_menu_principal_incluye_compras(db):
    """La tarjeta 'Compras' aparece para ADMINISTRADOR y enruta a ComprasWindow."""
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    sesion_global.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    try:
        menu = M.MenuPrincipal()
        assert "compras" in menu._cards
        menu.close()
    finally:
        sesion_global.usuario_actual = prev
    # Routing declarado en abrir_ventana_por_id.
    import inspect
    assert "ComprasWindow" in inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
