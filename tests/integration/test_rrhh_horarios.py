"""
F3.0.2 · Extracción de widgets RRHH (horarios/turnos/ausencias) con mover + shim.

Verifica que las 8 clases viven ahora en src/rrhh/gui/horarios.py, que gestion_usuarios
las sigue exportando (mismo objeto), que la herencia Qt se conserva, que instancian en
headless y que ConfiguracionWindow no sufre regresiones.
"""

import pytest

_CLASES = ("_HorarioComboBox", "_TurnoCelda", "_EmpNameEdit", "_HorarioLoadingWidget",
           "_AusenciaDialog", "_HorarioTable", "_HorarioSemana", "_HorarioContainer")


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


# 1. Import por ruta nueva
def test_import_ruta_nueva():
    from src.rrhh.gui import horarios as H
    for c in _CLASES:
        assert hasattr(H, c)


# 2. Import por ruta antigua (shim) intacto
def test_import_ruta_antigua():
    import src.gui.gestion_usuarios as gu
    for c in _CLASES:
        assert hasattr(gu, c)


# 3. Identidad de objetos (mismo objeto, no copia)
def test_identidad_objetos():
    import src.gui.gestion_usuarios as gu
    from src.rrhh.gui import horarios as H
    for c in _CLASES:
        assert getattr(gu, c) is getattr(H, c), f"{c} difiere entre rutas"


# 4. Instanciación headless
def test_instanciacion_headless():
    _app()
    from src.rrhh.gui import horarios as H
    assert H._HorarioComboBox() is not None
    assert H._HorarioLoadingWidget() is not None
    assert H._HorarioContainer() is not None
    assert H._HorarioSemana() is not None


# 5. Compatibilidad de herencia Qt
def test_herencia_qt():
    from PyQt6.QtWidgets import QComboBox, QDialog, QFrame, QWidget
    from src.rrhh.gui import horarios as H
    assert issubclass(H._HorarioComboBox, QComboBox)
    assert issubclass(H._AusenciaDialog, QDialog)
    assert issubclass(H._HorarioSemana, QFrame)
    for c in ("_TurnoCelda", "_EmpNameEdit", "_HorarioLoadingWidget",
              "_HorarioTable", "_HorarioContainer"):
        assert issubclass(getattr(H, c), QWidget)


# 6. Sin regresiones en ConfiguracionWindow
def test_configuracion_window_sin_regresion():
    _app()
    from src.gui.gestion_usuarios import ConfiguracionWindow
    w = ConfiguracionWindow(callback_vuelta=lambda: None,
                            usuario={"nombre": "T", "perfil": "ADMINISTRADOR"})
    assert w is not None
    w.close()


# Dependencias compartidas resueltas (anti-ciclo)
def test_dependencias_compartidas_resueltas():
    from src.rrhh.gui import horarios as H
    assert H._CIAN == "#00FFC6"
    assert callable(H._h_parse_minutes) and callable(H._dias_lg)
    assert H._MoveIcon is not None and H._RoundedItemDelegate is not None
