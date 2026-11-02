"""
SOMA restringido a SUPERADMIN: la pestaña "ASISTENTE SOMA" de Configuración (índice 11) queda
oculta y bloqueada para cualquier otro perfil — mismo patrón ya usado para "GENERAR PERFIL
EMPLEADO" (índice 2) en `gestion_usuarios.py::ConfiguracionWindow`. Smoke offscreen, sin BD (la
lógica de gating solo lee `sesion_global.usuario_actual`, igual que el resto de esta ventana).
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sesion(app):
    from src.db.usuario import sesion_global
    previo = sesion_global.usuario_actual
    yield sesion_global
    sesion_global.usuario_actual = previo


def test_superadmin_ve_la_pestana_soma(sesion):
    import src.gui.gestion_usuarios as gu
    sesion.usuario_actual = {"perfil": "SUPERADMIN", "nombre": "SUPER"}
    win = gu.ConfiguracionWindow()
    try:
        assert len(win.btns) >= 12 and win.btns[11] is not None
    finally:
        win.deleteLater()


def test_administrador_no_ve_la_pestana_soma(sesion):
    import src.gui.gestion_usuarios as gu
    sesion.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    win = gu.ConfiguracionWindow()
    try:
        assert len(win.btns) >= 12 and win.btns[11] is None
    finally:
        win.deleteLater()


def test_administrador_no_puede_abrir_soma_por_indice_directo(sesion, monkeypatch):
    """Defensa en profundidad: aunque se llame a `_cambiar_vista(11)` directamente (sin pasar por
    el botón, ya oculto), la vista NO cambia y se muestra un aviso de acceso restringido — mismo
    criterio que el bloqueo ya existente para `_cambiar_vista(2)`."""
    import src.gui.gestion_usuarios as gu
    sesion.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    avisos = []
    monkeypatch.setattr(gu, "mostrar_mensaje", lambda *a, **k: avisos.append(a))
    win = gu.ConfiguracionWindow()
    try:
        antes = win.stack.currentIndex()
        win._cambiar_vista(11)
        assert win.stack.currentIndex() == antes, "no debe cambiar a la pestaña SOMA"
        assert avisos, "debe mostrar un aviso de acceso restringido"
    finally:
        win.deleteLater()


def test_tab_inicial_11_no_abre_soma_para_administrador(sesion):
    """`ConfiguracionWindow(tab_inicial=11)` (p. ej. desde un enlace directo) tampoco debe abrir
    la pestaña SOMA para un perfil no autorizado — reutiliza la misma guarda de `btns[ti] is None`
    que ya protege esta vía para cualquier pestaña oculta."""
    import src.gui.gestion_usuarios as gu
    sesion.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    win = gu.ConfiguracionWindow(tab_inicial=11)
    try:
        assert win.stack.currentIndex() != 11
    finally:
        win.deleteLater()
