"""TPV Bakery — multiselección de productos + diálogo de cantidades múltiple.

La rejilla de productos permite marcar varios productos y sumarlos al carrito de una vez, indicando la
cantidad de cada uno. Qt offscreen; marca `db` porque la rejilla carga familias reales.
"""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

pytestmark = pytest.mark.db

_app = QApplication.instance() or QApplication([])


class _FakeTPV(QWidget):
    def __init__(self):
        super().__init__()
        self.added = []

    def _add_extra(self, cod, nom, pr, seccion="EXTRAS", cantidad=1):
        self.added.append((cod, cantidad))


def test_multiseleccion_toggle_y_boton_sumar(db):
    from src.gui.tpv import _RejillaProductosBakery
    ft = _FakeTPV()
    d = _RejillaProductosBakery(ft, parent=ft)

    assert d._btn_sumar.isEnabled() is False              # sin selección, no se puede sumar
    d._toggle({"codigo": "A", "nombre": "Croissant", "precio": 1.2, "emoji": ""})
    d._toggle({"codigo": "B", "nombre": "Pan", "precio": 0.9, "emoji": ""})
    assert set(d._seleccion) == {"A", "B"} and d._btn_sumar.isEnabled() is True
    d._toggle({"codigo": "A", "nombre": "Croissant", "precio": 1.2, "emoji": ""})   # desmarca A
    assert set(d._seleccion) == {"B"}


def test_dialogo_cantidad_multiple_pasos_y_clamp(db):
    from src.gui.tpv import _CantidadMultipleDialog
    prods = [{"codigo": "A", "nombre": "Croissant", "precio": 1.2, "emoji": "🥐"},
             {"codigo": "B", "nombre": "Pan", "precio": 0.9, "emoji": ""}]
    d = _CantidadMultipleDialog(prods)
    assert d.cantidades == {"A": 1, "B": 1}               # por defecto 1 cada uno
    d._paso("A", +1); d._paso("A", +1)                    # A = 3
    d._paso("B", -10)                                     # B no baja de 1 (clamp)
    assert d.cantidades == {"A": 3, "B": 1}
