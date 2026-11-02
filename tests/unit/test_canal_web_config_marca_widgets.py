"""
GUI (offscreen, BD real) de los nuevos controles de "Marca y configuración comercial" en
`CanalWebConfigDialog` (fix de usabilidad): color = botón-muestra con el selector unificado de la
app (nunca una barra de texto con el HEX a mano), moneda = desplegable con el catálogo de divisas
de la app (nunca texto libre), logo = subida de archivo + vista previa (nunca una URL a mano). Y el
reset in-situ de estos mismos campos al pulsar "Despublicar"."""

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
        cur.execute("UPDATE web_config SET color='#00FFC6', moneda='EUR', logo_url='' "
                   "WHERE id_empresa=%s", (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_color_es_un_boton_muestra_no_una_barra_de_texto(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        assert not hasattr(dlg, "inp_web_color")
        assert dlg._color_marca == "#00FFC6"
        assert hasattr(dlg, "_pintar_color_marca")
    finally:
        dlg.deleteLater()
    _ = app


def test_elegir_color_actualiza_el_estado_interno(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        dlg._pintar_color_marca("#FF0000")
        assert dlg._color_marca == "#FF0000"
    finally:
        dlg.deleteLater()
    _ = app


def test_moneda_es_un_desplegable_con_el_catalogo_de_divisas(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    from src.utils import divisas
    dlg = CanalWebConfigDialog()
    try:
        assert not hasattr(dlg, "inp_web_moneda")
        codigos = {dlg.cmb_web_moneda.itemData(i) for i in range(dlg.cmb_web_moneda.count())}
        assert set(divisas.monedas_soportadas()) <= codigos
        assert dlg.cmb_web_moneda.currentData() == "EUR"
        # El desplegable no debe cortar la etiqueta más larga del catálogo de divisas.
        assert dlg.cmb_web_moneda.view().minimumWidth() >= 300
    finally:
        dlg.deleteLater()
    _ = app


def test_logo_es_subida_de_archivo_no_una_url_a_mano(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        assert not hasattr(dlg, "inp_web_logo")
        assert dlg._logo_url_marca == ""
        assert hasattr(dlg, "_subir_logo_marca") and hasattr(dlg, "_quitar_logo_marca")
    finally:
        dlg.deleteLater()
    _ = app


def test_quitar_logo_limpia_el_estado(app, limpio):
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        dlg._logo_url_marca = "https://x.com/logo.png"
        dlg._quitar_logo_marca()
        assert dlg._logo_url_marca == ""
    finally:
        dlg.deleteLater()
    _ = app


def test_guardar_marca_usa_los_nuevos_campos(app, limpio):
    from src.db.empresa import empresa_actual_id
    from src.db import web_tienda
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        dlg.inp_web_nombre.setText("Tienda Widgets")
        dlg._pintar_color_marca("#00FF00")
        i = dlg.cmb_web_moneda.findData("USD")
        dlg.cmb_web_moneda.setCurrentIndex(i)
        dlg._logo_url_marca = "https://x.com/logo.png"
        dlg._guardar_marca()
        cfg = web_tienda.obtener_config(empresa_actual_id())
        assert cfg["color"] == "#00FF00" and cfg["moneda"] == "USD"
        assert cfg["logo_url"] == "https://x.com/logo.png"
    finally:
        dlg.deleteLater()
    _ = app


def test_despublicar_resetea_los_campos_ya_abiertos_del_dialogo(app, limpio, monkeypatch):
    from src.gui.canal_web_config import CanalWebConfigDialog
    import src.services.comercio_digital.canal_web as cw_mod
    monkeypatch.setattr(cw_mod, "despublicar", lambda **k: {"ok": True, "estado": "despublicado"})
    dlg = CanalWebConfigDialog()
    try:
        dlg.ck_web_activa.setChecked(True)
        dlg.inp_web_nombre.setText("Algo")
        dlg._pintar_color_marca("#123456")
        dlg._logo_url_marca = "https://x.com/l.png"
        dlg.ck_borrador.setChecked(True)
        dlg._acc_despublicar()
        assert dlg.ck_web_activa.isChecked() is False
        assert dlg.inp_web_nombre.text() == ""
        assert dlg._color_marca == "#00FFC6"
        assert dlg.cmb_web_moneda.currentData() == "EUR"
        assert dlg._logo_url_marca == ""
        assert dlg.ck_borrador.isChecked() is False
    finally:
        dlg.deleteLater()
    _ = app
