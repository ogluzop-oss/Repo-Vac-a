"""
F3.0.1 · Scaffolding del paquete RRHH y fachadas de compatibilidad.

Verifica que la nueva estructura `src/rrhh/` existe, que las fachadas reexportan
EXACTAMENTE los mismos objetos que las implementaciones originales (sin duplicar
lógica) y que la ventana de configuración sigue siendo importable e instanciable.
No se mueve código: estos tests garantizan compatibilidad total.
"""

import importlib

import pytest


# ── Estructura del paquete ────────────────────────────────────────────────────
def test_paquetes_rrhh_existen():
    for mod in ("src.rrhh", "src.rrhh.db", "src.rrhh.services", "src.rrhh.gui",
                "src.rrhh.documents", "src.rrhh.models"):
        assert importlib.import_module(mod) is not None


# ── Fachada GUI: misma clase, no una copia ────────────────────────────────────
def test_configuracion_window_es_la_misma_clase():
    from src.gui.gestion_usuarios import ConfiguracionWindow as Original
    from src.rrhh.gui.configuracion import ConfiguracionWindow as Fachada
    assert Fachada is Original                       # identidad, no duplicado


def test_import_antiguo_intacto():
    # El import histórico debe seguir funcionando sin cambios.
    from src.gui.gestion_usuarios import ConfiguracionWindow  # noqa: F401
    assert ConfiguracionWindow is not None


# ── Fachadas DB: reexportan los mismos callables ──────────────────────────────
def test_fachada_fichajes():
    from src.db import usuario as U
    from src.rrhh.db import fichajes as F
    for nombre in ("registrar_entrada", "registrar_salida", "listar_fichajes",
                   "obtener_fichaje_abierto", "validar_pin_fichaje"):
        assert getattr(F, nombre) is getattr(U, nombre)


def test_fachada_centros():
    from src.db import centros as C
    from src.rrhh.db import centros as RC
    for nombre in ("listar_centros", "obtener_centro", "centro_principal",
                   "crear_centro", "actualizar_centro", "marcar_principal", "baja_centro"):
        assert getattr(RC, nombre) is getattr(C, nombre)


def test_fachada_representantes():
    from src.db import representantes as R
    from src.rrhh.db import representantes as RR
    for nombre in ("listar_representantes", "obtener_representante", "representante_principal",
                   "crear_representante", "actualizar_representante", "marcar_principal",
                   "baja_representante"):
        assert getattr(RR, nombre) is getattr(R, nombre)


# ── Instanciación headless de la ventana (vía la fachada) ─────────────────────
def test_configuracion_window_instancia_headless():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    from src.rrhh.gui.configuracion import ConfiguracionWindow
    w = ConfiguracionWindow(callback_vuelta=lambda: None, usuario={"nombre": "T", "perfil": "ADMINISTRADOR"})
    assert w is not None
    w.close()
