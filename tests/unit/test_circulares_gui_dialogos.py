"""
`gui/circulares_gui.py` — dos bugs reales corregidos en esta sesión:

  1. `_DialogoBase(pantalla_completa=True)` abría los compositores/visores a ~35%x70% con borde
     turquesa en vez de pantalla completa sin bordes — fix: `QWidget.showFullScreen()` nativo en
     vez de `setGeometry(availableGeometry())` calculado a mano (ver `showEvent`).
  2. `_CampoDestinatarios` (Para/Cc/Cco) bloqueaba TODO el diálogo modal al escribir un email
     directamente (sin pasar por el desplegable de sugerencias) — causado por el grab implícito de
     `Qt.WindowType.Popup` anidado en un `QDialog` modal. Fix: `Qt.WindowType.ToolTip` (sin grab) +
     show/hide explícito (Escape, FocusOut con retardo, selección de item).

Smoke tests offscreen (QT_QPA_PLATFORM=offscreen en CI/headless): no se puede confirmar
visualmente que la ventana ocupa literalmente los píxeles de la pantalla, pero sí que Qt aplicó el
estado `WindowFullScreen` (lo que antes NUNCA ocurría con el `setGeometry` manual) y que el campo de
destinatarios admite tecleo real (`QTest.keyClicks`/`keyClick`) sin dejar el diálogo inoperante.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dialogobase_pantalla_completa_geometria_real_cubre_la_pantalla(app):
    """QUINTO intento del fix de pantalla completa. El log REAL del usuario tras el CUARTO intento
    (`showMaximized()`) reveló que `isMaximized()`/`windowState()` NO bastan como comprobación: Qt
    reportaba `WindowMaximized` mientras la geometría REAL era pequeña y centrada (sizeHint del
    contenido) — exactamente lo que el intento anterior afirmaba haber arreglado sin haberlo hecho.
    Este test comprueba la GEOMETRÍA REAL contra la de la pantalla, no solo la bandera de estado,
    y espera explícitamente al ciclo de eventos diferido (`QTimer.singleShot(0, ...)` en
    `showEvent`) que es la pieza nueva de este intento: Qt recentra el diálogo a su `sizeHint()`
    DESPUÉS de `showEvent` como parte de su propia secuencia interna de `show()` — por eso los 4
    intentos anteriores, que solo pedían pantalla completa DURANTE `showEvent`, veían su pedido
    deshecho después. Reaplicar en el ciclo de eventos siguiente es lo que debe sobrevivir a eso."""
    from src.gui.circulares_gui import _DialogoBase

    dlg = _DialogoBase("TEST PANTALLA COMPLETA", icono="✉️", pantalla_completa=True)
    try:
        assert bool(dlg.windowFlags() & Qt.WindowType.Window)
        dlg.show()
        app.processEvents()
        # Deja correr el ciclo de eventos para que el `QTimer.singleShot(0, ...)` diferido dispare
        # DESPUÉS de cualquier reajuste interno de QDialog — varias vueltas de processEvents(),
        # sin sleep real, para no depender de temporización de reloj en CI.
        for _ in range(10):
            app.processEvents()
        pantalla = dlg.screen() or app.primaryScreen()
        assert dlg.geometry() == pantalla.geometry(), (
            f"geometría real {dlg.geometry()} no coincide con la pantalla {pantalla.geometry()} "
            "— exactamente el fallo que reportó el usuario pese a isMaximized()=True")
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialogobase_sin_pantalla_completa_no_fuerza_fullscreen(app):
    from src.gui.circulares_gui import _DialogoBase

    dlg = _DialogoBase("TEST NORMAL", icono="📋", pantalla_completa=False)
    try:
        dlg.show()
        app.processEvents()
        assert not dlg.isFullScreen()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialogobase_pantalla_completa_no_se_puede_arrastrar(app):
    """Petición explícita: un diálogo a pantalla completa no debe poder moverse arrastrando desde
    la cabecera (no tendría sentido desplazar algo que ya ocupa toda la pantalla a propósito)."""
    from src.gui.circulares_gui import _DialogoBase

    dlg = _DialogoBase("TEST SIN ARRASTRE", icono="✉️", pantalla_completa=True)
    try:
        dlg.show()
        app.processEvents()
        pos_antes = dlg.pos()
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(50, 10), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        dlg.mousePressEvent(ev)
        assert dlg._drag is None, "no debe registrar el inicio de un arrastre en pantalla completa"
        ev_move = QMouseEvent(QEvent.Type.MouseMove, QPointF(200, 150), Qt.MouseButton.LeftButton,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        dlg.mouseMoveEvent(ev_move)
        assert dlg.pos() == pos_antes, "no debe haberse movido"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_campo_destinatarios_popup_ya_no_usa_qt_popup(app):
    """Causa raíz del freeze: `Qt.WindowType.Popup` conlleva un grab implícito de ratón/teclado que
    entraba en conflicto con el `QDialog` modal contenedor. Verifica que el fix sigue en vigor."""
    from src.gui.circulares_gui import _CampoDestinatarios

    campo = _CampoDestinatarios("Para")
    try:
        # Qt codifica el TIPO de ventana (Widget/Window/Dialog/Popup/ToolTip/...) en los bits bajos
        # como un CÓDIGO compuesto, no como banderas independientes — `Qt.WindowType.ToolTip` por
        # diseño de Qt comparte bits con `Popup` (ToolTip se construye sobre Popup internamente), así
        # que un simple `flags & Qt.WindowType.Popup` da positivo aunque el tipo real ya NO sea
        # Popup. La comparación correcta aísla el campo de tipo con `WindowType_Mask`.
        tipo = campo._popup.windowFlags() & Qt.WindowType.WindowType_Mask
        assert tipo == Qt.WindowType.ToolTip, tipo
        assert tipo != Qt.WindowType.Popup, tipo
    finally:
        campo.deleteLater()


def test_campo_destinatarios_escribir_email_directo_no_bloquea_el_dialogo(app):
    """Reproduce el escenario real del bug: `_CampoDestinatarios` dentro de un `QDialog` MODAL
    (`_DialogoBase`, `setModal(True)`), tecleando un email COMPLETO directamente (sin abrir nunca
    el desplegable de sugerencias) y pulsando Intro — exactamente el flujo que antes dejaba todo
    bloqueado. Usa `QTest.keyClicks`/`keyClick` (eventos reales de teclado), no llamadas internas."""
    from src.gui.circulares_gui import _CampoDestinatarios, _DialogoBase

    dlg = _DialogoBase("TEST CAMPO DESTINATARIOS", icono="✉️", pantalla_completa=False)
    campo = _CampoDestinatarios("Para")
    dlg.cuerpo.addWidget(campo)
    otro_boton = QPushButton("OTRO CAMPO")
    dlg.cuerpo.addWidget(otro_boton)
    try:
        # Modal pero NO bloqueante para el test: `show()` (no `exec()`) basta para activar el mismo
        # comportamiento de ventana modal que desencadenaba el bug, sin colgar el proceso de test.
        dlg.show()
        app.processEvents()

        campo.campo.setFocus()
        app.processEvents()
        QTest.keyClicks(campo.campo, "externo.directo@cliente.com")
        QTest.keyClick(campo.campo, Qt.Key.Key_Return)
        app.processEvents()

        # Se creó el chip de contacto externo (sin pasar nunca por el desplegable) y el campo de
        # texto quedó limpio — comportamiento esperado, SIN bloqueo.
        assert len(campo._chips) == 1
        identidad = campo._chips[0][0]
        assert identidad.get("email_externo") == "externo.directo@cliente.com"
        assert campo.campo.text() == ""

        # La prueba definitiva de "no bloqueado": el foco puede moverse a OTRO widget del mismo
        # diálogo con normalidad justo después. Con el bug real, el grab implícito de
        # `Qt.WindowType.Popup` dejaba esto inoperante hasta interactuar con el propio popup.
        otro_boton.setFocus()
        app.processEvents()
        assert otro_boton.hasFocus()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_campo_destinatarios_cc_y_cco_tambien_corregidos(app):
    """El usuario pidió explícitamente verificar que CC/Cco no sufren el mismo bloqueo que Para —
    misma clase `_CampoDestinatarios`, así que el fix (popup sin grab) aplica igual a las 3."""
    from src.gui.circulares_gui import _CampoDestinatarios, _DialogoBase

    dlg = _DialogoBase("TEST CC/CCO", icono="✉️", pantalla_completa=False)
    cc = _CampoDestinatarios("CC")
    cco = _CampoDestinatarios("Cco")
    dlg.cuerpo.addWidget(cc)
    dlg.cuerpo.addWidget(cco)
    try:
        dlg.show()
        app.processEvents()
        for campo, email in ((cc, "cc.directo@cliente.com"), (cco, "cco.directo@cliente.com")):
            tipo = campo._popup.windowFlags() & Qt.WindowType.WindowType_Mask
            assert tipo == Qt.WindowType.ToolTip, tipo
            campo.campo.setFocus()
            app.processEvents()
            QTest.keyClicks(campo.campo, email)
            QTest.keyClick(campo.campo, Qt.Key.Key_Return)
            app.processEvents()
            assert len(campo._chips) == 1
            assert campo._chips[0][0].get("email_externo") == email
    finally:
        dlg.close()
        dlg.deleteLater()
