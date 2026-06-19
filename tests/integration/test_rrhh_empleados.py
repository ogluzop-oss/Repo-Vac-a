"""
F3.0.3 · Extracción de diálogos RRHH de empleado (identificación/PIN/asignación).

Mover + shim: las 3 clases viven ahora en src/rrhh/gui/empleados.py; gestion_usuarios
las reexporta (mismo objeto). Sin regresiones ni ciclos de import.
"""

import pytest

_CLASES = ("_PinDialog", "_AsignarEmpleadoDialog", "_IdentificacionEmpleadoDialog")


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


# 1. Import por ruta nueva
def test_import_ruta_nueva():
    from src.rrhh.gui import empleados as E
    for c in _CLASES:
        assert hasattr(E, c)


# 2. Import por ruta antigua (shim)
def test_import_ruta_antigua():
    import src.gui.gestion_usuarios as gu
    for c in _CLASES:
        assert hasattr(gu, c)


# 3. Identidad de objetos
def test_identidad_objetos():
    import src.gui.gestion_usuarios as gu
    from src.rrhh.gui import empleados as E
    for c in _CLASES:
        assert getattr(gu, c) is getattr(E, c), f"{c} difiere entre rutas"


# 4. Instanciación headless
def test_instanciacion_headless():
    _app()
    from src.rrhh.gui import empleados as E
    assert E._PinDialog() is not None
    assert E._IdentificacionEmpleadoDialog() is not None
    assert E._AsignarEmpleadoDialog(id_caja="1") is not None   # firma real: requiere id_caja


# 5. Herencia Qt
def test_herencia_qt():
    from PyQt6.QtWidgets import QDialog
    from src.rrhh.gui import empleados as E
    for c in _CLASES:
        assert issubclass(getattr(E, c), QDialog)


# 6. ConfiguracionWindow sin regresión + diálogos de caja NO movidos intactos
def test_configuracion_window_y_caja_intactas():
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu.ConfiguracionWindow(callback_vuelta=lambda: None,
                               usuario={"nombre": "T", "perfil": "ADMINISTRADOR"})
    assert w is not None
    w.close()
    # Los diálogos de caja permanecen en el monolito (no se tocaron).
    for c in ("_MotivoDialog", "_SeleccionarCajaDialog", "_MovimientoDialog"):
        assert hasattr(gu, c)


# 7. Ausencia de ciclos de import (ambos órdenes resuelven en subproceso limpio)
def test_sin_ciclos_de_import():
    import subprocess
    import sys
    for stmt in (
        "from src.rrhh.gui.empleados import _PinDialog; import src.gui.gestion_usuarios as g; "
        "assert g._PinDialog is _PinDialog",
        "import src.gui.gestion_usuarios as g; from src.rrhh.gui import empleados as e; "
        "assert g._AsignarEmpleadoDialog is e._AsignarEmpleadoDialog",
    ):
        r = subprocess.run([sys.executable, "-c", stmt],
                           capture_output=True, text=True,
                           env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"})
        assert r.returncode == 0, r.stderr
