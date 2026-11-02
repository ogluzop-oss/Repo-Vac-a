"""
Cursores personalizados · el cursor de "cuatro flechas" (mover / `Qt.CursorShape.SizeAllCursor`)
se carga desde `assets/cursores/cursor 4 flechas.png` (pedido explícito), con el mismo mecanismo
ya usado para flecha/mano/texto/arrastrar — sin tocar ningún otro estado del cursor.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_cuatro_flechas_esta_en_el_mapa_de_ficheros_aceptados():
    from src.utils import cursores
    nombres_sizeall = next(nombres for nombres, forma in cursores._FICHEROS if forma == "SizeAllCursor")
    assert "cursor 4 flechas.png" in nombres_sizeall


def test_cargar_incluye_sizeall_cursor(app):
    from PyQt6.QtCore import Qt
    from src.utils import cursores
    mapa = cursores._cargar()
    assert Qt.CursorShape.SizeAllCursor in mapa


def test_sizeall_tiene_hotspot_centrado(app):
    from PyQt6.QtGui import QPixmap
    from src.utils import cursores
    pm = QPixmap(32, 32)
    hx, hy = cursores._hotspot("SizeAllCursor", pm)
    assert (hx, hy) == (16, 16)


def test_formas_preexistentes_siguen_intactas(app):
    """Añadir SizeAllCursor no debe desplazar ni romper los 5 estados ya existentes."""
    from src.utils import cursores
    formas = [forma for _, forma in cursores._FICHEROS]
    assert formas == ["ArrowCursor", "PointingHandCursor", "IBeamCursor", "OpenHandCursor",
                      "ClosedHandCursor", "SizeAllCursor"]


def test_instalar_no_revienta_con_el_nuevo_cursor(app):
    rem = None
    try:
        from src.utils import cursores
        rem = cursores.instalar(app)
    finally:
        if rem is not None:
            app.removeEventFilter(rem)
            app._remapeador_cursores = None
