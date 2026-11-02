"""
GUI (offscreen, BD real) del editor visual WYSIWYG del storefront (Fase 4 e-commerce,
`gui.tema_editor_dialog.TemaEditorDialog`): secciones reordenables, edición in-situ, IA por
bloque y guardado en `web_config.tema_json` vía el único editor ya existente."""

import json

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
        cur.execute("UPDATE web_config SET tema_json=NULL WHERE id_empresa=%s", (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_sin_tema_guardado_arranca_con_el_diseno_inicial(app, limpio):
    from src.gui.tema_editor_dialog import TemaEditorDialog, _SECCIONES_INICIALES
    dlg = TemaEditorDialog()
    try:
        assert [b["tipo"] for b in dlg._secciones] == list(_SECCIONES_INICIALES)
        assert dlg.lst_secciones.count() == len(_SECCIONES_INICIALES)
    finally:
        dlg.close()


def test_anadir_seccion_la_agrega_seleccionada_al_final(app, limpio):
    from src.gui.tema_editor_dialog import TemaEditorDialog
    dlg = TemaEditorDialog()
    try:
        n_antes = len(dlg._secciones)
        idx_hero = dlg.cmb_tipo_nuevo.findData("hero")
        dlg.cmb_tipo_nuevo.setCurrentIndex(idx_hero)
        dlg._anadir_seccion()
        assert len(dlg._secciones) == n_antes + 1
        assert dlg._secciones[-1]["tipo"] == "hero"
        assert dlg._idx_sel == n_antes
    finally:
        dlg.close()


def test_editar_campo_actualiza_la_seccion_y_dispara_el_debounce_de_preview(app, limpio):
    from src.gui.tema_editor_dialog import TemaEditorDialog
    dlg = TemaEditorDialog()
    try:
        idx_hero = dlg.cmb_tipo_nuevo.findData("hero")
        dlg.cmb_tipo_nuevo.setCurrentIndex(idx_hero)
        dlg._anadir_seccion()
        dlg._campo_cambiado("titulo", "Bienvenidos a mi tienda")
        assert dlg._secciones[dlg._idx_sel]["config"]["titulo"] == "Bienvenidos a mi tienda"
        assert dlg._debounce.isActive()
    finally:
        dlg.close()


def test_eliminar_seccion_la_quita_de_la_lista(app, limpio):
    from src.gui.tema_editor_dialog import TemaEditorDialog
    dlg = TemaEditorDialog()
    try:
        n_antes = len(dlg._secciones)
        dlg.lst_secciones.setCurrentRow(0)
        dlg._eliminar_seccion()
        assert len(dlg._secciones) == n_antes - 1
    finally:
        dlg.close()


def test_guardar_persiste_tema_json_y_se_lee_de_vuelta(app, limpio):
    from src.db import web_tienda
    from src.db.empresa import empresa_actual_id
    from src.gui.tema_editor_dialog import TemaEditorDialog
    dlg = TemaEditorDialog()
    try:
        idx_hero = dlg.cmb_tipo_nuevo.findData("hero")
        dlg.cmb_tipo_nuevo.setCurrentIndex(idx_hero)
        dlg._anadir_seccion()
        dlg._campo_cambiado("titulo", "Título de prueba")
        dlg._guardar()

        cfg = web_tienda.obtener_config(empresa_actual_id())
        tema = json.loads(cfg["tema_json"])
        assert any(s["tipo"] == "hero" and s["config"]["titulo"] == "Título de prueba"
                  for s in tema["secciones"])
    finally:
        dlg.close()


def test_generar_ia_sin_api_key_configurada_muestra_motivo_honesto(app, limpio, monkeypatch):
    from src.gui.tema_editor_dialog import TemaEditorDialog
    import src.services.catalogo.ia_contenido as ia_mod
    monkeypatch.setattr(ia_mod, "_cliente", lambda: None)
    dlg = TemaEditorDialog()
    try:
        idx_hero = dlg.cmb_tipo_nuevo.findData("hero")
        dlg.cmb_tipo_nuevo.setCurrentIndex(idx_hero)
        dlg._anadir_seccion()
        dlg._generar_ia("titulo")
        assert "no está configurado" in dlg.lbl_msg.text().lower()
    finally:
        dlg.close()


def test_abre_a_pantalla_completa_via_abrir_dialogo_deslizante(app, limpio, monkeypatch):
    """Bug real corregido: el botón "EDITOR VISUAL" de `CanalWebConfigDialog` llamaba a `.exec()`
    directo, sin pasar por `abrir_dialogo_deslizante` — el único punto que reafirma la geometría
    tras el asentamiento nativo de Windows (mismo bug que tenían las ventanas del módulo de
    correo). Aquí se confirma que ese botón YA usa el helper correcto."""
    import src.gui.canal_web_config as mod
    llamadas = []
    monkeypatch.setattr("src.gui.transiciones.abrir_dialogo_deslizante",
                        lambda dialog, origen: llamadas.append((dialog, origen)))
    dlg_cfg = mod.CanalWebConfigDialog()
    try:
        dlg_cfg._abrir_editor_visual()
        assert len(llamadas) == 1
        assert isinstance(llamadas[0][0], __import__(
            "src.gui.tema_editor_dialog", fromlist=["TemaEditorDialog"]).TemaEditorDialog)
    finally:
        dlg_cfg.deleteLater()


def test_ventana_fija_no_se_puede_arrastrar(app, limpio):
    """`moveEvent` debe reafirmar la geometría de pantalla completa si algo mueve la ventana
    (Windows permite mover una ventana sin barra de título por varias vías) — nunca se queda
    "arrastrada" fuera de su posición fija."""
    from PyQt6.QtCore import QPoint
    from src.gui.tema_editor_dialog import TemaEditorDialog
    dlg = TemaEditorDialog()
    try:
        dlg.show()
        correcta = dlg.pos()
        dlg.move(correcta + QPoint(150, 150))
        assert dlg.pos() == correcta
    finally:
        dlg.close()
