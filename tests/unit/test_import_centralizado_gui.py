"""
GUI (offscreen, BD real) de la centralización de importaciones (limpieza de duplicidades): las
pestañas "Importar Stock" (`gui.mostrar_stock._ImportarStockPage`) y "Importar Ventas"
(`gui.ventas.VentasAnaliticaWindow`, panel de previsión) ya no importan directamente desde aquí —
redirigen al módulo centralizado "Migrar datos"."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_importar_stock_page_sin_importacion_directa(app):
    import src.gui.mostrar_stock as mod
    w = mod._ImportarStockPage()
    try:
        assert not hasattr(w, "_importar")
        assert not hasattr(mod, "_ImportarHilo")
        assert hasattr(w, "_abrir_migracion_datos")
        assert w._btn.text() == "Ir a migrar datos"
    finally:
        w.deleteLater()
    _ = app


def test_importar_stock_abre_migracion_datos(app, monkeypatch):
    import src.gui.mostrar_stock as mod
    llamadas = []
    monkeypatch.setattr("src.gui.migracion_gui.MigracionDatosWindow",
                        lambda **k: llamadas.append(k) or _VentanaFalsa())
    w = mod._ImportarStockPage()
    try:
        w._abrir_migracion_datos()
        assert len(llamadas) == 1
    finally:
        w.deleteLater()
    _ = app


def test_importar_articulos_df_retirado():
    from src.db import articulos
    assert not hasattr(articulos, "importar_articulos_df")


def test_ventas_sin_pestana_importar_ventas(app, db):
    """La pestaña "Importar Ventas" (antes solo una redirección a "Migrar datos") se RETIRA por
    completo del sidebar — ya no debe quedar ni rastro de ella ni de su cluster de métodos, que
    quedaban huérfanos en cuanto se retira el botón que los llamaba."""
    import src.gui.ventas as mod
    w = mod.VentasAnaliticaWindow()
    try:
        assert not hasattr(mod, "_ImportarHistoricoHilo")
        assert not hasattr(w, "_subir_ventas_pasadas")
        assert not hasattr(w, "_panel_prevision")
        assert not hasattr(w, "_abrir_migracion_datos")
        assert not hasattr(w, "btn_subir_hist")
        assert len(w._sidebar_btns) == 3
        assert [b.text() for b in w._sidebar_btns] == [
            "RESUMEN DE VENTAS", "RENDIMIENTO", "PRODUCTIVIDAD"]
    finally:
        w.close()


class _VentanaFalsa:
    def setWindowFlag(self, *_a, **_k):
        pass

    def showMaximized(self):
        pass
