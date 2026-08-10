"""
Tests · Portal Web operativo (reforma). Tras retirar las secciones que duplicaban módulos del ERP, se
conservan las vistas delgadas que SÍ pertenecen al Back Office: **Buscador global** (agrega los buscadores
existentes) y los **componentes reutilizables** (PanelTabla paginación/filtro/export, FormPanel). N7: sin
motor nuevo.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── 1 · Buscador global agrega los buscadores existentes ──────────────────────
def test_buscador_global():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.portal_web_ui.buscador_global import SeccionBuscadorGlobal
    s = SeccionBuscadorGlobal()
    s._buscar("a")  # no debe fallar; agrega clientes/artículos/pedidos/reservas
    assert s.panel is not None


# ── 2 · Componentes reutilizables (PanelTabla, FormPanel) ─────────────────────
def test_componentes_web10():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.portal_web_ui.componentes import FormPanel, PanelTabla
    pt = PanelTabla(page_size=2)
    pt.cargar(["a", "b"], [{"a": i, "b": f"x{i}"} for i in range(5)])
    assert pt._paginas() == 3
    pt._filtrar("x3")
    assert len(pt._filtrado) == 1
    pt._ir(0)
    assert pt.tabla.rowCount() >= 1
    # FormPanel emite el dict capturado.
    fp = FormPanel()
    fp.configurar("T", (("nombre", "Nombre"), ("nif", "NIF")), {"nombre": "Ana"})
    capt = {}
    fp.guardado.connect(lambda d: capt.update(d))
    fp._emit()
    assert capt.get("nombre") == "Ana" and "nif" in capt
