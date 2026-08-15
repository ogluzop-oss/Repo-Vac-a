"""foundation.layout.reflow_grid — rejilla adaptativa sin huecos (para paneles que ocultan botones
según edición/permisos). Sin BD; solo Qt offscreen."""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QGridLayout, QPushButton, QWidget  # noqa: E402

from src.gui.foundation.layout import reflow_grid  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _posiciones(grid):
    pos = {}
    for i in range(grid.count()):
        r, c, _rs, _cs = grid.getItemPosition(i)
        pos[grid.itemAt(i).widget().text()] = (r, c)
    return pos


def test_reflow_sin_huecos():
    cont = QWidget(); g = QGridLayout(cont)
    btns = [QPushButton(str(i)) for i in range(8)]     # 8 visibles (p. ej. báscula oculta)
    filas = reflow_grid(g, btns, cols=3)
    pos = _posiciones(g)
    assert filas == 3
    assert pos["0"] == (0, 0) and pos["1"] == (0, 1) and pos["2"] == (0, 2)
    assert pos["3"] == (1, 0)                            # la 2ª fila empieza en col 0 (sin hueco)
    assert pos["7"] == (2, 1)
    assert g.count() == 8                                # exactamente los visibles, ni uno más


def test_reflow_refluye_al_reordenar():
    cont = QWidget(); g = QGridLayout(cont)
    a, b, c = QPushButton("a"), QPushButton("b"), QPushButton("c")
    reflow_grid(g, [a, b, c], cols=3)
    # quitar 'b' (se oculta en cierta edición) → 'c' debe subir a la posición de 'b', sin hueco
    reflow_grid(g, [a, c], cols=3)
    pos = _posiciones(g)
    assert g.count() == 2 and pos["a"] == (0, 0) and pos["c"] == (0, 1)


def test_reflow_vacio():
    cont = QWidget(); g = QGridLayout(cont)
    assert reflow_grid(g, [], cols=3) == 0 and g.count() == 0
