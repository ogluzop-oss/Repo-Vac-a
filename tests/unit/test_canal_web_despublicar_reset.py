"""
Canal Web · Despublicar es un RESET completo (no una simple pausa): la marca/configuración
comercial vuelve a sus valores por defecto y el canal deja de "existir" para la automatización de
Canal Web — `abrir_canal_web` vuelve a mostrar la pregunta inicial hasta que se publique de nuevo.
Publicar/regenerar siguen funcionando igual después (la fila técnica/credenciales no se destruyen)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db

EMP = "T-CW-DESPUB-RESET"
GER = {"perfil": "ADMINISTRADOR", "id": "g"}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_canal_web WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_canal_dominios WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_despublicar_resetea_la_marca_a_los_valores_por_defecto(limpia):
    from src.db import web_tienda
    from src.services.comercio_digital import canal_web
    canal_web.crear({"nombre": "Tienda X"}, id_empresa=EMP, usuario=GER)
    canal_web.guardar_presencia(id_empresa=EMP, usuario=GER, nombre="Mi Tienda",
                                descripcion="Lo mejor", color="#FF0000", moneda="USD",
                                logo_url="https://x.com/logo.png", dominio="x.com",
                                texto_terminos="T&C", tema_json='{"secciones":[]}')
    canal_web.despublicar(id_empresa=EMP, usuario=GER)
    cfg = web_tienda.obtener_config(EMP)
    assert cfg["nombre"] == "" and cfg["descripcion"] == ""
    assert cfg["color"] == "#00FFC6" and cfg["moneda"] == "EUR"
    assert cfg["logo_url"] == "" and cfg["dominio"] == ""
    assert cfg["texto_terminos"] == "" and cfg["tema_json"] == ""
    assert int(cfg["activa"]) == 0


def test_despublicar_hace_que_el_canal_deje_de_existir(limpia):
    from src.services.comercio_digital import canal_web
    canal_web.crear({"nombre": "Tienda X"}, id_empresa=EMP, usuario=GER)
    assert canal_web.existe(EMP) is True
    canal_web.despublicar(id_empresa=EMP, usuario=GER)
    assert canal_web.existe(EMP) is False


def test_republicar_tras_despublicar_sigue_funcionando(limpia):
    """La fila técnica/credenciales del canal NO se destruyen: publicar/regenerar funcionan igual
    después de un despublicar, aunque la marca haya vuelto a sus valores por defecto."""
    from src.services.comercio_digital import canal_web, conexiones
    canal_web.crear({"nombre": "Tienda X"}, id_empresa=EMP, usuario=GER)
    tok1 = conexiones.credenciales("web", id_empresa=EMP).get("api_key")
    canal_web.despublicar(id_empresa=EMP, usuario=GER)
    r = canal_web.publicar(id_empresa=EMP, usuario=GER)
    assert r["ok"] is True and r["estado"] == "publicado"
    assert canal_web.existe(EMP) is True
    r2 = canal_web.regenerar(id_empresa=EMP, usuario=GER)
    assert r2["ok"] is True
    tok2 = conexiones.credenciales("web", id_empresa=EMP).get("api_key")
    assert tok1 and tok2 and tok1 != tok2


def test_abrir_canal_web_tras_despublicar_muestra_la_pregunta_de_nuevo(app, limpia):
    from src.gui.canal_web_gui import CanalWebWindow, abrir_canal_web
    from src.services.comercio_digital import canal_web
    canal_web.crear({"nombre": "Tienda X"}, id_empresa=EMP, usuario=GER)
    canal_web.despublicar(id_empresa=EMP, usuario=GER)
    w = abrir_canal_web(id_empresa=EMP)
    try:
        assert isinstance(w, CanalWebWindow)
        assert w._stack.currentIndex() == 0
    finally:
        w.close()
