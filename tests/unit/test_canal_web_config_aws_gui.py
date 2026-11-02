"""
GUI (offscreen, BD real) del botón "Publicar en AWS" en `CanalWebConfigDialog` (Fase 5
e-commerce): el mensaje mostrado debe reflejar el modo REAL devuelto por el servicio (nunca dice
"publicado en AWS" si en realidad fue al backend local degradado)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def storage_local(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    from src.services import storage as S
    S._reset_para_tests()
    yield
    S._reset_para_tests()


def test_boton_publicar_aws_existe_y_llama_al_servicio(app, storage_local, monkeypatch):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        assert hasattr(dlg, "_acc_publicar_aws")
        dlg._acc_publicar_aws()
        texto = dlg.lbl_msg.text().lower()
        # Sin AWS real configurada, el modo es "simulado": nunca debe decir "publicado en AWS".
        assert "publicado en aws" not in texto
        assert "vista previa local" in texto or "no se pudo" in texto
    finally:
        dlg.deleteLater()
    _ = app


def test_mensaje_honesto_cuando_el_servicio_dice_modo_aws(app, monkeypatch):
    from src.gui.canal_web_config import CanalWebConfigDialog
    import src.services.comercio_digital.canal_web as cw_mod
    monkeypatch.setattr(cw_mod, "publicar_aws",
                        lambda **k: {"ok": True, "modo": "aws", "url": "https://bucket.s3.amazonaws.com/x"})
    dlg = CanalWebConfigDialog()
    try:
        dlg._acc_publicar_aws()
        assert "publicado en aws" in dlg.lbl_msg.text().lower()
    finally:
        dlg.deleteLater()
    _ = app
