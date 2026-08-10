"""
Fase 2: asistente Enterprise de Migración de datos (smoke offscreen). Ejerce el flujo completo sin diálogo de
archivo: cargar fichero → mapeo auto-sugerido → simular → importar, verificando que carga en `articulos`.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_asistente_flujo_completo(app, fab, db, tmp_path, monkeypatch):
    import src.gui.migracion_gui as MG
    monkeypatch.setattr(MG, "mostrar_mensaje", lambda *a, **k: None)   # evita el modal en headless
    fab._borrar("articulos", "codigo", "IMPGUI-1")
    fab._borrar("stock_tienda", "codigo_articulo", "IMPGUI-1")
    fab._borrar("movimientos_stock", "codigo_articulo", "IMPGUI-1")

    ruta = tmp_path / "cat.csv"
    ruta.write_text("codigo;nombre;precio;stock\nIMPGUI-1;Producto GUI;2,50;9\n", encoding="utf-8")

    win = MG.MigracionDatosWindow(usuario={"perfil": "ADMINISTRADOR"})
    try:
        asis = win.asistente                                  # pestaña construida en el arranque (lazy)
        asis.cargar_fichero(str(ruta))
        assert asis.stack.currentIndex() == 1                 # pasó a "confirmar mapeo"
        assert asis._combos["codigo"].currentData() == "codigo"   # auto-mapeo correcto
        asis._simular()
        assert asis.stack.currentIndex() == 2                 # pasó a "revisión"
        asis._importar()
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT nombre, Stock_total FROM articulos WHERE codigo='IMPGUI-1'")
            r = cur.fetchone()
        assert r and r[0] == "Producto GUI" and r[1] == 9     # cargado por el asistente
    finally:
        win.deleteLater()
