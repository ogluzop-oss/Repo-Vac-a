"""
GUI (offscreen, BD real) de la barra de acciones de "Marketplace · Integraciones Comerciales"
(`IntegracionesComercialesWindow`): todos los botones comparten el mismo diseño exacto que "Añadir
integración" (borde grueso + negrita + relleno al hover) — "Eliminar" en rojo y al final de la
fila — y los emojis de Sincronizar/Reintentar/Actualizar son los pedidos explícitamente."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QPushButton

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_eliminar_esta_al_final_y_en_rojo(app, db):
    from src.gui.integraciones_comerciales_gui import IntegracionesComercialesWindow, _ROJO
    win = IntegracionesComercialesWindow(id_empresa="T-IC-BTN")
    try:
        botones = win.findChildren(QPushButton)
        etiquetas = [b.text() for b in botones if "integración" in b.text().lower()
                    or b.text().strip("↔️🔃🔄✔⚙🗑＋ ") in
                    ("Configurar", "Validar", "Sincronizar", "Reintentar", "Actualizar", "Eliminar")]
        assert etiquetas, "no se encontró la barra de acciones"
        assert "Eliminar" in etiquetas[-1]
        btn_eliminar = next(b for b in botones if "Eliminar" in b.text())
        assert _ROJO in btn_eliminar.styleSheet()
        # Mismo diseño que "Añadir integración" (borde 2px + negrita 900), no el diseño secundario
        # (borde 1px) que tenían antes Configurar/Validar/etc.
        assert "border:2px solid" in btn_eliminar.styleSheet()
    finally:
        win.close()


def test_mismo_diseno_que_anadir_integracion_para_todos_los_botones(app, db):
    from src.gui.integraciones_comerciales_gui import IntegracionesComercialesWindow
    win = IntegracionesComercialesWindow(id_empresa="T-IC-BTN2")
    try:
        botones = {b.text(): b for b in win.findChildren(QPushButton)}
        b_add = next(b for t, b in botones.items() if "integración" in t.lower())
        for etiqueta in ("Configurar", "Validar", "Sincronizar", "Reintentar", "Actualizar"):
            b = next(b for t, b in botones.items() if etiqueta in t)
            assert "border:2px solid" in b.styleSheet()
            assert "font-weight:900" in b.styleSheet()
    finally:
        win.close()


def test_emojis_pedidos_explicitamente(app, db):
    from src.gui.integraciones_comerciales_gui import IntegracionesComercialesWindow
    win = IntegracionesComercialesWindow(id_empresa="T-IC-BTN3")
    try:
        botones = [b.text() for b in win.findChildren(QPushButton)]
        assert any(t.startswith("↔️") and "Sincronizar" in t for t in botones)
        assert any(t.startswith("🔃") and "Reintentar" in t for t in botones)
        assert any(t.startswith("🔄") and "Actualizar" in t for t in botones)
    finally:
        win.close()
