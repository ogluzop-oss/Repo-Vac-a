"""
GUI (offscreen, BD real) de la sección "Borrador con contraseña" en `CanalWebConfigDialog`
(Fase 5 e-commerce): activar exige contraseña, desactivar no, y dejarla en blanco con el borrador
ya activo es un no-op honesto (nunca rota el hash sin una contraseña nueva escrita)."""

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
        cur.execute("UPDATE web_config SET borrador=0, password_hash=NULL WHERE id_empresa=%s",
                   (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_activar_sin_contrasena_muestra_motivo_honesto(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        dlg.ck_borrador.setChecked(True)
        dlg.inp_borrador_pass.setText("")
        dlg._guardar_borrador()
        assert "contraseña" in dlg.lbl_msg.text().lower()
    finally:
        dlg.deleteLater()
    _ = app


def test_activar_con_contrasena_persiste_y_se_refleja_en_bd(app, limpio):
    from src.db.empresa import empresa_actual_id
    from src.db import web_tienda
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        dlg.ck_borrador.setChecked(True)
        dlg.inp_borrador_pass.setText("claveSegura1")
        dlg._guardar_borrador()
        assert "activado" in dlg.lbl_msg.text().lower()
        cfg = web_tienda.obtener_config(empresa_actual_id())
        assert int(cfg["borrador"]) == 1 and cfg["password_hash"]
        assert dlg.inp_borrador_pass.text() == ""   # se limpia tras guardar
    finally:
        dlg.deleteLater()
    _ = app


def test_dejar_contrasena_en_blanco_con_borrador_activo_es_no_op(app, limpio):
    from src.services.comercio_digital import canal_web as _cw
    from src.gui.canal_web_config import CanalWebConfigDialog
    GER = {"perfil": "ADMINISTRADOR", "id": "g"}
    _cw.configurar_borrador(activar=True, password="original1", usuario=GER)
    dlg = CanalWebConfigDialog()
    try:
        dlg.ck_borrador.setChecked(True)
        dlg.inp_borrador_pass.setText("")
        dlg._guardar_borrador()
        assert "ya estaba activo" in dlg.lbl_msg.text().lower()
    finally:
        dlg.deleteLater()
    _ = app


def test_desactivar_no_exige_contrasena(app, limpio):
    from src.db.empresa import empresa_actual_id
    from src.db import web_tienda
    from src.services.comercio_digital import canal_web as _cw
    from src.gui.canal_web_config import CanalWebConfigDialog
    GER = {"perfil": "ADMINISTRADOR", "id": "g"}
    _cw.configurar_borrador(activar=True, password="original1", usuario=GER)
    dlg = CanalWebConfigDialog()
    try:
        dlg.ck_borrador.setChecked(False)
        dlg.inp_borrador_pass.setText("")
        dlg._guardar_borrador()
        assert "desactivado" in dlg.lbl_msg.text().lower()
        cfg = web_tienda.obtener_config(empresa_actual_id())
        assert int(cfg["borrador"]) == 0
    finally:
        dlg.deleteLater()
    _ = app
