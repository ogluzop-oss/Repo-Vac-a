"""Bolsa de proveedores · UI en Pedidos (Fase 1 · paso 2).

Verifica el flujo: buscar un artículo → tabla-bolsa con proveedores/precio ordenada por precio → añadir la
tarifa seleccionada a un pedido BORRADOR (cola). Qt offscreen; `db`. Se fija la empresa activa para que el
tenant de la UI coincida con los datos sembrados.
"""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

pytestmark = pytest.mark.db

_app = QApplication.instance() or QApplication([])


def test_bolsa_buscar_y_anadir_a_pedido(db, fab, monkeypatch):
    from src.db import empresa as EMP
    from src.db import proveedores as PROV
    from src.db import compras as C
    from src.services.compras import proveedores_pro as PP
    import src.gui.compras_gestion as CG

    emp = fab.empresa("EMP bolsa UI")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)
    monkeypatch.setattr(CG, "_aviso", lambda *a, **k: None)   # sin modales bloqueantes

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedor_precios_negociados WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                        "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
            cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    p_caro = PROV.crear_proveedor("Caro SL", id_empresa=emp)
    p_barato = PROV.crear_proveedor("Barato SL", id_empresa=emp)
    PP.set_precio_negociado(p_caro, "ARTUI", 9.0, unidad_medida="unidad", id_empresa=emp)
    PP.set_precio_negociado(p_barato, "ARTUI", 6.0, unidad_medida="unidad", id_empresa=emp)

    w = CG.ComprasWindow(usuario={"nombre": "Tester"})

    # Buscar en la bolsa → dos filas, ordenadas por precio (más barato primero).
    w.in_bolsa_art.setText("ARTUI")
    w._buscar_bolsa()
    assert w.tbl_bolsa.rowCount() == 2
    assert w.tbl_bolsa.item(0, 0).text() == "Barato SL"       # el más barato arriba
    assert w.tbl_bolsa.item(0, 3).text() == "6.00"             # precio neto

    # Añadir la tarifa seleccionada (la más barata) a un pedido BORRADOR.
    w.tbl_bolsa.setCurrentCell(0, 0)
    w.in_bolsa_cant.setText("4")
    w._bolsa_add_pedido()

    pedidos = C.listar_pedidos(id_empresa=emp, estado="BORRADOR", id_proveedor=p_barato)
    assert len(pedidos) == 1
    ped = C.obtener_pedido(pedidos[0]["id_pedido"], id_empresa=emp)
    assert ped and ped["estado"] == "BORRADOR"
    lineas = ped.get("lineas") or []
    assert any(l.get("codigo_articulo") == "ARTUI" and int(l.get("cantidad")) == 4 for l in lineas)
