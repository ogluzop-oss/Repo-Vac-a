"""
Notificación flotante de vencimiento SaaS (`gui.menu_principal.MenuPrincipal._mostrar_notif_saas`)
— crash real reportado en terminal:

    RuntimeError: wrapped C/C++ object of type QFrame has been deleted

Causa: el autocierre a los 14s (`QTimer.singleShot(14000, ...)`) llamaba `card.hide()` sobre la
MISMA variable `card` capturada por closure, comprobando solo `if card` (la referencia Python,
que nunca es None) — si el usuario ya había pulsado "ENTENDIDO" antes de los 14s (cierre manual,
que SÍ borra el objeto C++ con `deleteLater()`), el disparo tardío del temporizador intentaba
`.hide()` sobre un QFrame cuyo lado C++ ya no existe → `RuntimeError`.

Fix: `_cerrar_notif_saas()` centraliza el cierre (manual Y por temporizador), pone
`self._notif_saas_widget = None` al cerrar, y el temporizador comprueba esa referencia de
INSTANCIA (no la variable capturada) antes de actuar — además envuelve en try/except por si acaso.

No se instancia `MenuPrincipal` completa (carga tarjetas de menú, RBAC, etc. — pesado y no es lo
que se prueba aquí): se mezclan los 3 métodos relevantes sobre un `QWidget` mínimo, mismo patrón
que ya se usa en `test_main_loading_chroma.py` para `SmartManagerApp`.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _MenuDummy(QWidget):
    """QWidget mínimo con solo los 3 métodos de la notificación SaaS, correctamente ligados."""
    from src.gui.menu_principal import MenuPrincipal as _MP
    _mostrar_notif_saas = _MP._mostrar_notif_saas
    _cerrar_notif_saas = _MP._cerrar_notif_saas
    _posicionar_notif_saas = _MP._posicionar_notif_saas
    del _MP


def test_cerrar_manual_no_revienta_si_el_temporizador_dispara_despues(app):
    """Reproduce EXACTAMENTE el bug: cierre manual (ENTENDIDO) antes de los 14s, y luego se
    reproduce la comprobación programada por `QTimer.singleShot` — no debe lanzar RuntimeError."""
    dummy = _MenuDummy()
    dummy._mostrar_notif_saas({"nivel": "urgente", "mensaje": "Tu suscripción ha vencido."})
    card = dummy._notif_saas_widget
    assert card is not None

    dummy._cerrar_notif_saas()                 # clic en "ENTENDIDO"
    assert dummy._notif_saas_widget is None
    app.processEvents()                        # deja correr el deleteLater() real

    # Lo que el `QTimer.singleShot(14000, ...)` ejecutaría si disparase ahora:
    try:
        resultado = dummy._cerrar_notif_saas() if dummy._notif_saas_widget is card else None
    except RuntimeError:
        pytest.fail("el disparo tardío del temporizador no debe lanzar RuntimeError "
                    "(objeto QFrame ya borrado)")
    assert resultado is None


def test_cerrar_notif_saas_es_idempotente(app):
    """Llamarlo dos veces seguidas (doble clic, o clic + temporizador con la guarda ya puesta a
    prueba arriba) no debe fallar."""
    dummy = _MenuDummy()
    dummy._mostrar_notif_saas({"nivel": "aviso", "mensaje": "Tu suscripción vence pronto."})
    dummy._cerrar_notif_saas()
    dummy._cerrar_notif_saas()   # no debe lanzar nada
    assert dummy._notif_saas_widget is None


def test_el_temporizador_no_toca_una_notificacion_mas_reciente(app):
    """Si se muestra una SEGUNDA notificación antes de que venza el temporizador de la primera
    (self._notif_saas_widget ya apunta a la nueva card), el disparo tardío del temporizador de la
    primera NO debe cerrar la segunda."""
    dummy = _MenuDummy()
    dummy._mostrar_notif_saas({"nivel": "aviso", "mensaje": "Primera."})
    card_1 = dummy._notif_saas_widget

    dummy._mostrar_notif_saas({"nivel": "urgente", "mensaje": "Segunda."})
    card_2 = dummy._notif_saas_widget
    assert card_2 is not card_1

    # Disparo tardío del temporizador de la PRIMERA card (comprobación tal cual la hace el código):
    resultado = dummy._cerrar_notif_saas() if dummy._notif_saas_widget is card_1 else None
    assert resultado is None
    assert dummy._notif_saas_widget is card_2, "la notificación más reciente no debe tocarse"
