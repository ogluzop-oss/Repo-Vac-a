"""
Tests · Fase WEB-08 — Migración de `_GestionPedidosOnlineDialog` (TPV) → `PortalWebHome` (Portal Web).

Verifica (reorganización arquitectónica, sin desarrollar funcionalidades):
  1. `PortalWebHome` vive en `gui/portal_web_home.py`, instancia offscreen (ambas ramas: asistente y
     operativo) y conserva el alias de compatibilidad `_GestionPedidosOnlineDialog`.
  2. El módulo `portal_web_home` NO importa `gui.tpv` a nivel de módulo (los diálogos POS reutilizados
     se importan de forma perezosa en el punto de uso).
  3. El TPV ya NO contiene `_GestionPedidosOnlineDialog` y solo ABRE el Portal Web (router →
     PortalWebWindow); no importa `PortalWebHome`.
  4. `PortalWebWindow` es el shell de navegación (8 secciones), con `PortalWebHome` como pantalla inicial
     y las secciones reservadas mostrando el marcador "en preparación".
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── 1 · Núcleo extraído + alias ───────────────────────────────────────────────
def test_portal_web_home_instancia_y_alias():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from src.gui.portal_web_home import (PortalWebHome,
                                         _GestionPedidosOnlineDialog)
    app = QApplication.instance() or QApplication([])
    assert _GestionPedidosOnlineDialog is PortalWebHome
    # Rama asistente (sin canal en BD de test) + rama operativa (forzada).
    w = PortalWebHome(empleado="EMP", id_caja="C1")
    assert w is not None
    PortalWebHome._canal_existe = lambda self: True
    w2 = PortalWebHome(empleado="EMP", id_caja="C1")
    assert hasattr(w2, "tabla")
    _ = app


# ── 2 · Autonomía del módulo (no importa tpv a nivel de módulo) ───────────────
def test_portal_web_home_no_importa_tpv_a_nivel_modulo():
    import inspect

    from src.gui import portal_web_home
    # Recorre solo las líneas de import de primer nivel (col 0); las importaciones de tpv deben ser
    # perezosas (dentro de métodos, indentadas).
    for ln in inspect.getsource(portal_web_home).splitlines():
        if ln.startswith(("import ", "from ")):
            assert "gui.tpv" not in ln, ln


# ── 3 · TPV desacoplado: solo router a PortalWebWindow ────────────────────────
def test_tpv_sin_gestion_pedidos_y_abre_portal():
    import inspect

    from src.gui import tpv
    assert not hasattr(tpv, "_GestionPedidosOnlineDialog")
    assert not hasattr(tpv, "PortalWebHome")
    src = inspect.getsource(tpv)
    assert "import portal_web_home" not in src
    assert "from src.gui.portal_web_home" not in src
    assert "portal_web_gui import PortalWebWindow" in src  # el TPV solo ABRE el Portal Web


# ── 4 · Shell de navegación (WEB-09: Inicio como pantalla inicial, Pedidos = núcleo) ──────────
def test_portal_web_window_shell_navegacion():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from PyQt6.QtWidgets import QScrollArea

    from src.gui.portal_web_gui import PortalWebWindow
    from src.gui.portal_web_home import PortalWebHome
    app = QApplication.instance() or QApplication([])
    w = PortalWebWindow(empleado="EMP", id_caja="C1")
    assert len(w._botones) == 3               # reforma: Inicio · Buscador global · Pedidos online
    assert w.seccion_actual() == "inicio"     # pantalla inicial = dashboard
    # Navegar al núcleo: "Pedidos online" reutiliza PortalWebHome (WEB-08), envuelto en scroll.
    w._navegar("pedidos")
    cur = w._stack.currentWidget()
    assert isinstance(cur, QScrollArea) and isinstance(cur.widget(), PortalWebHome)
    # Compatibilidad de firma (WEB-07) + navegación por firma flexible.
    assert PortalWebWindow(id_empresa="E-PW") is not None
    _ = app
