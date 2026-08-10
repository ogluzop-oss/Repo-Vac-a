"""
Visor de EDICIÓN en Configuración (segmentación por tipo de comercio). Verifica que la pestaña existe y que
lista todas las funciones segmentables con su estado (activa/oculta/sustituida). Smoke offscreen.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_pestana_edicion_en_configuracion(app):
    import src.gui.gestion_usuarios as gu
    from src.services import verticales
    win = gu.ConfiguracionWindow(usuario={"perfil": "ADMINISTRADOR", "nombre": "tester"})
    try:
        assert 14 in win._page_builders                    # builder de la pestaña EDICIÓN registrado
        assert len(win.btns) >= 15 and win.btns[14] is not None
        win._ensure_page(14)                               # construye la página (lazy)
        assert win._tabla_edicion.rowCount() == len(verticales.FUNCIONES)   # lista toda la matriz
    finally:
        win.deleteLater()
