"""
Migrar datos · Centro obligatorio (pedido explícito): la migración debe ir SIEMPRE al centro/tienda
al que está conectado el usuario — nunca "a todos los centros" ni a un centro por defecto
arbitrario. Sin contexto operativo activo, el asistente ni se construye (igual patrón que
`gui/registro_temperatura_gui.py` para "sin tienda asignada")."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_flag_migracion():
    """Evita contaminación entre tests: algunos construyen `_AsistenteMigracion` directamente (sin
    pasar por `MigracionDatosWindow.closeEvent`, el único punto fiable que limpia el flag — ver su
    comentario sobre `destroyed` no siendo fiable para una ventana de nivel superior)."""
    import src.gui.migracion_gui as mod
    mod._estado_migracion["en_curso"] = False
    yield
    mod._estado_migracion["en_curso"] = False


@pytest.fixture
def sin_tienda():
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(None)
    yield
    emp_db.set_tienda_actual(previa)


@pytest.fixture
def con_tienda():
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(1)
    yield
    emp_db.set_tienda_actual(previa)


def test_sin_centro_conectado_no_construye_el_asistente(app, db, sin_tienda):
    from src.gui.migracion_gui import _AsistenteMigracion
    w = _AsistenteMigracion(usuario={"perfil": "SUPERADMIN"})
    try:
        assert not hasattr(w, "_stack")   # el wizard real nunca se construyó
        assert not hasattr(w, "_entidad")
    finally:
        w.deleteLater()


def test_con_centro_conectado_construye_el_asistente_normalmente(app, db, con_tienda):
    from src.gui.migracion_gui import _AsistenteMigracion
    w = _AsistenteMigracion(usuario={"perfil": "ADMINISTRADOR"})
    try:
        assert hasattr(w, "_stack")
        assert w._id_tienda_migracion == 1
    finally:
        w.deleteLater()


def test_commit_pasa_el_id_tienda_de_la_sesion_al_motor(app, db, con_tienda, monkeypatch):
    from src.gui.migracion_gui import _CommitWorker
    import src.gui.migracion_gui as mod
    llamadas = []
    monkeypatch.setattr(mod._imp, "commit", lambda *a, **k: llamadas.append(k) or {"ok": True})
    worker = _CommitWorker("lote-x", tamano_lote=50, id_tienda=1)
    worker.run()
    assert llamadas[0]["id_tienda"] == 1


def test_flag_en_curso_activo_mientras_la_ventana_esta_abierta(app, db, con_tienda):
    import src.gui.migracion_gui as mod
    assert mod.migracion_en_curso() is False
    w = mod.MigracionDatosWindow(usuario={"perfil": "ADMINISTRADOR"})
    try:
        assert mod.migracion_en_curso() is True
    finally:
        w.close()
    assert mod.migracion_en_curso() is False


def test_selector_centro_bloqueado_mientras_hay_migracion_en_curso(app, db, con_tienda, monkeypatch):
    import src.gui.migracion_gui as mig_mod
    import src.gui.menu_principal as menu_mod
    monkeypatch.setattr(mig_mod, "_estado_migracion", {"en_curso": True})
    llamadas = []
    monkeypatch.setattr(menu_mod, "mostrar_mensaje", lambda *a, **k: llamadas.append(1))

    class _MenuFalso:
        _abrir_selector_centro = menu_mod.MenuPrincipal._abrir_selector_centro

    m = _MenuFalso()
    m._abrir_selector_centro()
    assert llamadas == [1]   # se avisó, nunca se abrió el selector real
