"""TPV — el login de caja (_LoginTPVDialog) se muestra sin parpadeo blanco.

El diálogo es frameless+translúcido y se abre DURANTE la construcción del TPV (la ventana padre aún no
tiene geometría). Para evitar que aparezca mal colocado (sobre la tarjeta TPV del menú) y con un primer
frame blanco, se mapea invisible (opacidad 0) y se revela ya centrado (opacidad 1). Qt offscreen; `db`
porque el diálogo carga la lista de empleados.
"""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

pytestmark = pytest.mark.db

_app = QApplication.instance() or QApplication([])


def test_login_tpv_no_flash_blanco(db):
    from src.gui.tpv import _LoginTPVDialog
    d = _LoginTPVDialog()
    # Al crearse (antes de mapearse) es INVISIBLE → nada de flash blanco ni salto de posición.
    assert d.windowOpacity() == 0.0
    # Tras centrarse (lo que hace el showEvent diferido) se revela pintado y centrado.
    d._centrar_en_pantalla()
    assert d.windowOpacity() == 1.0
