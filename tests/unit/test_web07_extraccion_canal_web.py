"""
Tests · Fase WEB-07 — Extracción definitiva del Canal Web del TPV + entrada a Portal Web.

Verifica (arquitectura, sin desarrollar Portal Web):
  1. El diálogo de configuración del Canal Web vive en `gui/canal_web_config.py` (extraído de tpv.py) y
     es AUTÓNOMO (no importa tpv.py).
  2. El TPV ya NO contiene la clase de configuración del Canal Web y su código-fuente no importa
     `canal_web_config` (desacoplamiento privado TPV↔Canal Web).
  3. La ventana de entrada del Portal Web (placeholder reservado) instancia offscreen.
  4. La redirección "Web" del Catálogo y el asistente Canal Web apuntan al módulo extraído (Canal Web
     sigue funcionando desde su propio módulo, no desde el TPV).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── 1 · Config del Canal Web extraída y autónoma ──────────────────────────────
def test_canal_web_config_instancia_offscreen():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from src.gui.canal_web_config import (CanalWebConfigDialog,
                                          _CanalWebConfigDialog)
    app = QApplication.instance() or QApplication([])
    dlg = CanalWebConfigDialog()
    assert dlg is not None
    # La tabla de conexiones y el botón de marca se construyen (diálogo completo, no stub).
    assert hasattr(dlg, "tabla") and hasattr(dlg, "inp_web_nombre")
    # Alias de compatibilidad Strangler conservado.
    assert _CanalWebConfigDialog is CanalWebConfigDialog
    _ = app


def test_canal_web_config_no_importa_tpv():
    import inspect

    from src.gui import canal_web_config
    src = inspect.getsource(canal_web_config)
    # Autónomo: copia sus helpers, no importa nada de gui.tpv.
    assert "gui.tpv" not in src and "from src.gui.tpv" not in src


# ── 2 · El TPV ya no contiene la config del Canal Web y está desacoplado ───────
def test_tpv_sin_clase_config_canal_web():
    import inspect

    from src.gui import tpv
    # La clase de configuración del Canal Web ya no existe como atributo del módulo TPV.
    assert not hasattr(tpv, "_CanalWebConfigDialog")
    src = inspect.getsource(tpv)
    # El TPV no IMPORTA el módulo de configuración del Canal Web (la mención en el comentario-marcador
    # Strangler es solo documental). Solo navega a Portal Web.
    assert "import canal_web_config" not in src
    assert "from src.gui.canal_web_config" not in src
    assert "portal_web_gui import PortalWebWindow" in src  # el TPV abre el Portal Web


# ── 3 · Entrada Portal Web (placeholder reservado) ────────────────────────────
def test_portal_web_window_offscreen():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from src.gui.portal_web_gui import PortalWebWindow
    app = QApplication.instance() or QApplication([])
    w = PortalWebWindow(id_empresa="E-PW")
    assert w is not None
    _ = app


# ── 4 · Canal Web sigue alcanzable desde su propio módulo y desde Catálogo ─────
def test_catalogo_y_canal_web_apuntan_al_modulo_extraido():
    import inspect

    from src.gui import canal_web_gui, catalogo_gestion
    # WEB-12: Catálogo ENTRA en Canal Web por su módulo (la pregunta inicial), no abriendo la config directa.
    # La cadena hasta el módulo EXTRAÍDO se mantiene: catalogo → canal_web_gui → canal_web_config.
    assert "canal_web_gui" in inspect.getsource(catalogo_gestion)
    assert "from src.gui.tpv import _CanalWebConfigDialog" not in inspect.getsource(catalogo_gestion)
    # El módulo Canal Web abre su configuración desde el módulo extraído (autosuficiente, no el TPV).
    assert "canal_web_config" in inspect.getsource(canal_web_gui)
