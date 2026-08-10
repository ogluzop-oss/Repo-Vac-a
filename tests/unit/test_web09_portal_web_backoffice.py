"""
Tests · Portal Web · Back Office (reforma). El shell navega por las secciones que QUEDAN tras la reforma —
Inicio (dashboard) · Buscador global · Pedidos online (núcleo `PortalWebHome`) — con lazy loading y scroll.
Las secciones Reservas/Encargos/Stock/Logística/Clientes/Configuración se retiraron (duplicaban módulos
propios del ERP). Componentes reutilizables intactos. Vistas delgadas sin SQL.
"""

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── 1 · Cada sección que queda instancia offscreen ────────────────────────────
def test_secciones_instancian_offscreen():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.portal_web_ui.buscador_global import SeccionBuscadorGlobal
    from src.gui.portal_web_ui.inicio import SeccionInicio
    assert SeccionInicio() is not None
    assert SeccionBuscadorGlobal() is not None


# ── 2 · Shell navega con lazy loading por las 3 secciones (todas con scroll) ──
def test_shell_navega_lazy_secciones():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from PyQt6.QtWidgets import QScrollArea

    from src.gui.portal_web_gui import _NAV, PortalWebWindow
    from src.gui.portal_web_home import PortalWebHome
    assert [c for c, _ in _NAV] == ["inicio", "buscador", "pedidos"]
    w = PortalWebWindow(empleado="EMP", id_caja="C1")
    assert w.seccion_actual() == "inicio" and len(w._cache) == 1   # lazy
    for clave, _t in _NAV:
        w._navegar(clave)
        assert w._stack.currentWidget() is w._cache[clave]
    assert len(w._cache) == 3
    # "Pedidos online" = núcleo PortalWebHome, envuelto en scroll (scrollbars en TODAS las secciones).
    w._navegar("pedidos")
    cur = w._stack.currentWidget()
    assert isinstance(cur, QScrollArea) and isinstance(cur.widget(), PortalWebHome)


# ── 3 · Componentes reutilizables ─────────────────────────────────────────────
def test_componentes_reutilizables():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.portal_web_ui.componentes import (Breadcrumb, Buscador,
                                                   KpiCard, PanelSeccion,
                                                   TablaDatos, Toolbar)
    kpi = KpiCard("Ventas", "10", "hoy")
    kpi.set_valor(20, "actualizado")
    tabla = TablaDatos()
    tabla.cargar(["A", "B"], [[1, 2], [3, 4]])
    assert tabla.rowCount() == 2 and tabla.columnCount() == 2
    bc = Breadcrumb()
    bc.set_ruta(["Portal Web", "Inicio"])
    assert "Inicio" in bc.text()
    assert Buscador() is not None and Toolbar() is not None and PanelSeccion("X").cuerpo is not None


# ── 4 · Vistas delgadas: la sección Inicio no ejecuta SQL directo ─────────────
def test_seccion_sin_sql():
    from src.gui.portal_web_ui import inicio
    s = inspect.getsource(inicio)
    assert "obtener_conexion" not in s and "cursor(" not in s
