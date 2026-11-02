"""
Fase 3 (e-commerce, Catálogo Web) — políticas legales de la tienda (términos/privacidad/
devoluciones/envíos) y acceso directo a la pasarela de pago desde `CanalWebConfigDialog`.

Políticas legales: 4 columnas TEXT nuevas en `web_config` (migración 0290), editadas vía el MISMO
único editor ya establecido (`canal_web.guardar_presencia` → `db.web_tienda.guardar_config`) —
sin tabla ni función de guardado nuevas. Pasarela de pago: el diálogo (antes solo en `gui/tpv.py`)
se extrajo a un módulo neutral (`gui/pasarela_config_dialog.py`) para poder reutilizarse desde
Canal Web sin romper el desacoplamiento TPV↔Canal Web ya establecido y testeado
(`test_web07_extraccion_canal_web.py::test_canal_web_config_no_importa_tpv`)."""

import pytest

pytestmark = pytest.mark.db

EMP = "T-CW-F3-LEGAL"
GER = {"perfil": "ADMINISTRADOR", "id": "g3"}


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


# ── db.web_tienda: columnas nuevas ────────────────────────────────────────────

def test_obtener_config_incluye_los_4_campos_legales_vacios_por_defecto(limpia):
    from src.db import web_tienda
    cfg = web_tienda.obtener_config(EMP)
    for campo in ("texto_terminos", "texto_privacidad", "texto_devoluciones", "texto_politica_envios"):
        assert cfg[campo] == ""


def test_guardar_config_persiste_los_4_campos_legales(limpia):
    from src.db import web_tienda
    ok = web_tienda.guardar_config(
        id_empresa=EMP, texto_terminos="T&C de prueba", texto_privacidad="Privacidad de prueba",
        texto_devoluciones="Devoluciones de prueba", texto_politica_envios="Envíos de prueba")
    assert ok is True
    cfg = web_tienda.obtener_config(EMP)
    assert cfg["texto_terminos"] == "T&C de prueba"
    assert cfg["texto_privacidad"] == "Privacidad de prueba"
    assert cfg["texto_devoluciones"] == "Devoluciones de prueba"
    assert cfg["texto_politica_envios"] == "Envíos de prueba"


def test_guardar_marca_no_borra_las_politicas_legales_ya_guardadas(limpia):
    """Regresión real: `guardar_config` solo debe tocar los campos indicados — guardar la marca
    (nombre/color/...) sin pasar los textos legales NO debe vaciarlos."""
    from src.db import web_tienda
    web_tienda.guardar_config(id_empresa=EMP, texto_terminos="No me borres")
    web_tienda.guardar_config(id_empresa=EMP, nombre="Mi Tienda")
    cfg = web_tienda.obtener_config(EMP)
    assert cfg["texto_terminos"] == "No me borres"
    assert cfg["nombre"] == "Mi Tienda"


# ── comercio_digital.canal_web: passthrough (único editor) ──────────────────

def test_guardar_presencia_acepta_los_campos_legales_sin_cambios_de_codigo(limpia):
    """`guardar_presencia(**campos)` ya reenvía cualquier kwarg a `web_tienda.guardar_config` — este
    test confirma que sigue siendo así tras añadir los campos legales (no se filtran)."""
    from src.services.comercio_digital import canal_web
    r = canal_web.guardar_presencia(id_empresa=EMP, usuario=GER, texto_terminos="Vía canal_web")
    assert r["ok"] is True
    cp = canal_web.config_presencia(EMP)
    assert cp["texto_terminos"] == "Vía canal_web"


def test_guardar_presencia_legal_respeta_rbac(limpia):
    from src.services.comercio_digital import canal_web
    r = canal_web.guardar_presencia(id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"},
                                    texto_terminos="no debería guardarse")
    assert r.get("error") == "forbidden"


# ── GUI: CanalWebConfigDialog (offscreen) ────────────────────────────────────

def test_dialogo_tiene_los_4_campos_legales_y_el_boton_de_pasarela():
    import pytest as _pytest
    _pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.canal_web_config import CanalWebConfigDialog
    dlg = CanalWebConfigDialog()
    try:
        assert set(dlg._campos_legales) == {"texto_terminos", "texto_privacidad",
                                            "texto_devoluciones", "texto_politica_envios"}
        assert hasattr(dlg, "_abrir_pasarela_pago")
    finally:
        dlg.deleteLater()
    _ = app


def test_aplicar_plantilla_rellena_el_campo_sin_tocar_los_demas():
    import pytest as _pytest
    _pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.canal_web_config import CanalWebConfigDialog, _PLANTILLA_TERMINOS
    dlg = CanalWebConfigDialog()
    try:
        dlg._aplicar_plantilla_legal("texto_terminos", _PLANTILLA_TERMINOS)
        assert dlg._campos_legales["texto_terminos"].toPlainText() == _PLANTILLA_TERMINOS
        assert dlg._campos_legales["texto_privacidad"].toPlainText() == ""
    finally:
        dlg.deleteLater()
    _ = app


def test_guardar_legal_desde_el_dialogo_persiste_en_bd(limpia):
    import pytest as _pytest
    _pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.db import web_tienda
    from src.db.empresa import empresa_actual_id
    from src.gui.canal_web_config import CanalWebConfigDialog
    emp_actual = empresa_actual_id()
    dlg = CanalWebConfigDialog()
    try:
        dlg._campos_legales["texto_devoluciones"].setPlainText("Devoluciones desde GUI")
        dlg._guardar_legal()
        cfg = web_tienda.obtener_config(emp_actual)
        assert cfg["texto_devoluciones"] == "Devoluciones desde GUI"
    finally:
        with __import__("src.db.conexion", fromlist=["obtener_conexion"]).obtener_conexion() as conn, \
                conn.cursor() as cur:
            cur.execute("UPDATE web_config SET texto_devoluciones=NULL WHERE id_empresa=%s", (emp_actual,))
            conn.commit()
        dlg.deleteLater()
    _ = app


def test_abrir_pasarela_pago_abre_el_dialogo_correcto(monkeypatch):
    """No se abre un `.exec()` real (bloquearía el test) — se comprueba que el manejador intenta
    abrir la clase correcta, monkeypatcheando solo el punto de entrada del diálogo."""
    import pytest as _pytest
    _pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.canal_web_config import CanalWebConfigDialog
    import src.gui.pasarela_config_dialog as mod_pasarela

    llamadas = []

    class _DialogoFalso:
        def __init__(self, parent=None):
            llamadas.append(parent)

        def exec(self):
            llamadas.append("exec")

    monkeypatch.setattr(mod_pasarela, "PasarelaConfigDialog", _DialogoFalso)
    dlg = CanalWebConfigDialog()
    try:
        dlg._abrir_pasarela_pago()
        assert llamadas == [dlg, "exec"]
    finally:
        dlg.deleteLater()
    _ = app
