"""
Canal Web · Flujo directo (automatización UX, limpieza/auto Fase 2 e-commerce): si el canal YA
está configurado (`canal_web.existe`), `abrir_canal_web()` se salta la pregunta inicial "¿tu
empresa ya dispone de web?" y abre directamente la gestión (`CanalWebConfigDialog`, con acceso
inmediato al Editor Visual) — nunca hace repetir un cuestionario ya respondido. Un canal SIN
configurar sigue mostrando la pregunta, sin cambios."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db

EMP = "T-CW-FLUJO-DIRECTO"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_canal_web WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_sin_canal_configurado_muestra_la_pregunta(app, limpia):
    from src.gui.canal_web_gui import CanalWebWindow, abrir_canal_web
    w = abrir_canal_web(id_empresa=EMP)
    try:
        assert isinstance(w, CanalWebWindow)
        assert w._stack.currentIndex() == 0
    finally:
        w.close()


def test_con_canal_ya_configurado_salta_directo_a_la_gestion(app, limpia, monkeypatch):
    from src.services.comercio_digital import canal_web
    canal_web.crear({"nombre": "Tienda ya creada"}, publicacion={"tipo": "subdominio", "nombre": "flujodirecto"},
                    id_empresa=EMP)
    assert canal_web.existe(EMP) is True

    llamadas = []
    import src.gui.canal_web_gui as mod

    class _DialogoFalso:
        def __init__(self, parent=None):
            llamadas.append(("crear", parent))

        def close(self):
            llamadas.append(("close",))

    def _abrir_falso(dialog, origen):
        llamadas.append(("abrir_deslizante", dialog, origen))

    monkeypatch.setattr("src.gui.canal_web_config.CanalWebConfigDialog", _DialogoFalso)
    monkeypatch.setattr("src.gui.transiciones.abrir_dialogo_deslizante", _abrir_falso)

    resultado = mod.abrir_canal_web(id_empresa=EMP)
    assert isinstance(resultado, _DialogoFalso)
    assert llamadas[0][0] == "crear"
    assert llamadas[1][0] == "abrir_deslizante"
