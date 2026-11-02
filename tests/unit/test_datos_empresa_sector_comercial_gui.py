"""
Configuración · "Datos de empresa" · sección "Sector Comercial" (pedido explícito): desplegable
ancho con las 5 ediciones del software (Supermarket/Retail/Pharmacy/Textil/Bakery), que permite
cambiar `empresas.sector_id` para desbloquear la entrada al Portal B2B.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _ventana(usuario=None):
    import src.gui.gestion_usuarios as gu
    from src.db.usuario import sesion_global
    sesion_global.usuario_actual = usuario or {"id": 1, "perfil": "ADMINISTRADOR", "nombre": "tester"}
    win = gu.ConfiguracionWindow(usuario=sesion_global.usuario_actual)
    win._ensure_page(9)   # "Datos de empresa" (lazy)
    return win


def test_seccion_sector_comercial_existe_con_las_5_ediciones(app, db):
    from src.services import verticales
    win = _ventana()
    try:
        assert hasattr(win, "_de_sector")
        assert win._de_sector.count() == len(verticales.VERTICALES)
        etiquetas = [win._de_sector.itemText(i) for i in range(win._de_sector.count())]
        assert etiquetas == ["Supermarket", "Retail", "Pharmacy", "Textil", "Bakery & Coffee"]
    finally:
        win.deleteLater()


def test_desplegable_sector_es_lo_bastante_ancho(app, db):
    win = _ventana()
    try:
        assert win._de_sector.minimumWidth() >= 260
        assert win._de_sector.view().minimumWidth() >= 260
    finally:
        win.deleteLater()


def test_guardar_datos_empresa_persiste_sector_elegido(app, db, fab, monkeypatch):
    import src.gui.gestion_usuarios as gu
    from src.db import empresa as emp_db
    from src.db.usuario import sesion_global
    # `_de_guardar_empresa` muestra un `mostrar_mensaje` MODAL (`.exec()`) al terminar — en headless
    # se queda esperando para siempre sin esto (mismo patrón ya usado en otros tests de GUI que
    # disparan un diálogo de confirmación).
    monkeypatch.setattr(gu, "mostrar_mensaje", lambda *a, **k: None)
    eid = fab.empresa("SECTOR GUI TEST")
    sesion_global.usuario_actual = {"id": 1, "perfil": "ADMINISTRADOR", "nombre": "tester"}
    from src.db.empresa import set_empresa_actual
    previa = emp_db.empresa_actual_id()
    set_empresa_actual(eid)
    win = _ventana()
    try:
        ix = win._de_sector.findText("Pharmacy")
        assert ix >= 0
        win._de_sector.setCurrentIndex(ix)
        win._de_guardar_empresa()
        guardado = emp_db.obtener_empresa(eid)
        assert guardado is not None
        assert int(guardado["sector_id"]) == win._de_sector.currentData()
    finally:
        win.deleteLater()
        set_empresa_actual(previa)
