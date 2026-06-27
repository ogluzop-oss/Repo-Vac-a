"""
BLOQUE 8.3 — integración Qt del escáner universal + QSS táctil.
Requiere QApplication offscreen; no necesita hardware ni BD.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _key(texto: str, key: int = 0) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, texto)


def test_filtro_emite_codigo_en_rafaga(app):
    from src.gui.escaner_qt import FiltroEscaner
    w = QWidget()
    f = FiltroEscaner(w)
    recibidos = []
    f.codigo_escaneado.connect(recibidos.append)
    for ch in "8412345678905":
        f.eventFilter(w, _key(ch))
    f.eventFilter(w, _key("", Qt.Key.Key_Return))   # terminador
    assert recibidos == ["8412345678905"]


def test_filtro_no_consume_por_defecto(app):
    from src.gui.escaner_qt import FiltroEscaner
    w = QWidget()
    f = FiltroEscaner(w)
    # Una pulsación normal no se consume (deja pasar el evento a los campos).
    assert f.eventFilter(w, _key("a")) is False


def test_instalar_escaner_conecta_callback(app):
    from src.gui.escaner_qt import instalar_escaner
    w = QWidget()
    out = []
    filtro = instalar_escaner(w, out.append)
    for ch in "ABC123":
        filtro.eventFilter(w, _key(ch))
    filtro.eventFilter(w, _key("\t", Qt.Key.Key_Tab))
    assert out == ["ABC123"]


def test_qss_tactil_normal_es_vacio(app):
    from src.utils import perfil_tactil
    import assets.estilo_global as eg
    perfil_tactil.set_perfil("normal")
    assert eg._qss_tactil() == ""


def test_qss_tactil_tpv_aumenta_objetivos(app):
    from src.utils import perfil_tactil
    import assets.estilo_global as eg
    perfil_tactil.set_perfil("tpv")
    s = eg._qss_tactil()
    assert "min-height: 56px" in s and "QPushButton" in s
    perfil_tactil.set_perfil("normal")  # restaurar
