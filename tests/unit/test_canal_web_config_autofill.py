"""
Canal Web · Configuración cero-esfuerzo (automatización UX, Fase 2 e-commerce): el campo "Nombre
de la tienda" se sugiere automáticamente desde el nombre comercial YA conocido por el ERP cuando
todavía no hay nombre propio guardado — nunca inventa nada que el ERP no tenga."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def limpio(db):
    from src.db.empresa import EMPRESA_DEFAULT_ID
    def _clean(cur):
        cur.execute("UPDATE web_config SET nombre='' WHERE id_empresa=%s", (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_sin_nombre_propio_sugiere_el_nombre_comercial_del_erp(app, limpio):
    from src.db.empresa import empresa_actual_id, obtener_empresa
    from src.gui.canal_web_config import CanalWebConfigDialog
    nombre_erp = (obtener_empresa(empresa_actual_id()) or {}).get("nombre_comercial") or \
                 (obtener_empresa(empresa_actual_id()) or {}).get("nombre_empresa") or ""
    dlg = CanalWebConfigDialog()
    try:
        assert dlg.inp_web_nombre.text() == nombre_erp
    finally:
        dlg.deleteLater()
    _ = app


def test_con_nombre_propio_ya_guardado_no_lo_sobreescribe(app, limpio):
    from src.services.comercio_digital import canal_web
    from src.gui.canal_web_config import CanalWebConfigDialog
    GER = {"perfil": "ADMINISTRADOR", "id": "g"}
    canal_web.guardar_presencia(usuario=GER, nombre="Mi Nombre Propio De Tienda")
    dlg = CanalWebConfigDialog()
    try:
        assert dlg.inp_web_nombre.text() == "Mi Nombre Propio De Tienda"
    finally:
        dlg.deleteLater()
    _ = app
