"""
Catálogo Online · pestaña "Web propia": el botón "ADMINISTRAR CANAL WEB" se retiró (automatización
UX) — `abrir_canal_web` ya decide por sí mismo si hay que mostrar la pregunta inicial o saltar
directo a la gestión cuando el canal YA existe, así que un segundo botón que hacía exactamente lo
mismo era un acceso redundante."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QPushButton

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_panel_web_no_tiene_boton_administrar_ni_metodo(app, db):
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        assert not hasattr(win, "_administrar_canal_web")
        panel = win._panel_web()
        textos = [b.text() for b in panel.findChildren(QPushButton)]
        assert any("Abrir canal web" in t for t in textos)
        assert not any("Administrar" in t for t in textos)
    finally:
        win.close()
    _ = app
