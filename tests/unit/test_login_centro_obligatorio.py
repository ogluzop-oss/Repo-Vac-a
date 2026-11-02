"""
Login · Centro obligatorio para SUPERADMIN (pedido explícito), SIN bloquear el login: el diálogo
modal antiguo (`main.py::_exigir_centro_superadmin`, un bucle que se abría ANTES de ocultar el
overlay de carga) se retiró porque se solapaba con la animación. Ahora el SUPERADMIN entra directo
al Menú Principal y, una vez pintado (diferido), `main.py::_abrir_selector_centro_tras_login`
delega en `MenuPrincipal._abrir_selector_centro(es_login=True)` — el MISMO diálogo del chip de la
esquina superior izquierda. Degrada honestamente sin bloquear si todavía no hay ningún centro dado
de alta (instalación nueva). Cerrar ese diálogo auto-abierto SIN elegir centro redirige de vuelta
al selector de perfil (igual que un logout); reabierto luego a mano desde el chip, cerrarlo sin
elegir no hace nada especial."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _app_stub(menu_principal=None):
    """Instancia mínima con el método real de `SmartManagerApp` enlazado — evita construir la app
    completa (reproductores de audio, SOMA, overlays...) solo para probar este método."""
    import src.main as mod
    stub = QWidget()
    stub.menu_principal = menu_principal
    stub._abrir_selector_centro_tras_login = \
        mod.SmartManagerApp._abrir_selector_centro_tras_login.__get__(stub)
    return stub


def _menu_stub():
    """Idem para `MenuPrincipal._abrir_selector_centro`/`_volver_a_selector_perfil`/
    `_cerrar_recursos` — se enlazan los métodos REALES (no reimplementados en el test) sobre un
    `QWidget` ligero con los atributos mínimos que `_cerrar_recursos` necesita (`_cerrando`,
    `_ventanas`)."""
    import src.gui.menu_principal as mod
    stub = QWidget()
    stub._abrir_selector_centro = mod.MenuPrincipal._abrir_selector_centro.__get__(stub)
    stub._volver_a_selector_perfil = mod.MenuPrincipal._volver_a_selector_perfil.__get__(stub)
    stub._cerrar_recursos = mod.MenuPrincipal._cerrar_recursos.__get__(stub)
    stub._cerrando = False
    stub._ventanas = {}
    stub._recargado = []
    stub._recargar_contexto_tienda = lambda: stub._recargado.append(1)
    return stub


# ── main.py::_abrir_selector_centro_tras_login (el gate que decide SI hace falta abrir algo) ──
def test_con_centro_ya_activo_no_abre_nada(app, db, monkeypatch):
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(1)
    try:
        llamadas = []
        menu = _menu_stub()
        menu._abrir_selector_centro = lambda **k: llamadas.append(k)
        s = _app_stub(menu_principal=menu)
        s._abrir_selector_centro_tras_login({"id": "u1", "perfil": "SUPERADMIN"})
        assert llamadas == []
    finally:
        emp_db.set_tienda_actual(previa)


def test_sin_centro_y_sin_centros_dados_de_alta_no_bloquea(app, db, monkeypatch):
    """Degradación honesta: instalación nueva sin ningún centro creado — no se puede exigir una
    elección imposible."""
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(None)
    try:
        monkeypatch.setattr("src.db.centros.listar_centros", lambda *a, **k: [])
        llamadas = []
        menu = _menu_stub()
        menu._abrir_selector_centro = lambda **k: llamadas.append(k)
        s = _app_stub(menu_principal=menu)
        s._abrir_selector_centro_tras_login({"id": "u1", "perfil": "SUPERADMIN"})
        assert llamadas == []
    finally:
        emp_db.set_tienda_actual(previa)


def test_sin_centro_pero_hay_centros_disponibles_delega_en_el_menu(app, db, monkeypatch):
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(None)
    try:
        monkeypatch.setattr("src.db.centros.listar_centros",
                            lambda *a, **k: [{"id_centro": 1, "tipo_centro": "tienda"}])
        llamadas = []
        menu = _menu_stub()
        menu._abrir_selector_centro = lambda **k: llamadas.append(k)
        s = _app_stub(menu_principal=menu)
        s._abrir_selector_centro_tras_login({"id": "u1", "perfil": "SUPERADMIN"})
        assert llamadas == [{"es_login": True}]
    finally:
        emp_db.set_tienda_actual(previa)


def test_sin_menu_principal_aun_construido_no_revienta(app, db, monkeypatch):
    from src.db import empresa as emp_db
    previa = emp_db.tienda_actual_id()
    emp_db.set_tienda_actual(None)
    try:
        monkeypatch.setattr("src.db.centros.listar_centros",
                            lambda *a, **k: [{"id_centro": 1, "tipo_centro": "tienda"}])
        s = _app_stub(menu_principal=None)
        s._abrir_selector_centro_tras_login({"id": "u1", "perfil": "SUPERADMIN"})  # no debe lanzar
    finally:
        emp_db.set_tienda_actual(previa)


# ── menu_principal.py::_abrir_selector_centro(es_login=...) — el diálogo en sí ──────────────
class _DialogoFalso:
    def __init__(self, resultado, **_k):
        self._resultado = resultado

    def exec(self):
        pass

    def get_resultado(self):
        return self._resultado


def test_es_login_true_y_se_elige_centro_recarga_contexto(app, db, monkeypatch):
    monkeypatch.setattr("src.gui.migracion_gui.migracion_en_curso", lambda: False)
    monkeypatch.setattr("src.gui.selector_tienda.SelectorCentroDialog",
                        lambda *a, **k: _DialogoFalso({"ok": True}))
    menu = _menu_stub()
    logout_llamado = []
    menu.detectar_logout = lambda: logout_llamado.append(1)
    menu._abrir_selector_centro(es_login=True)
    assert menu._recargado == [1]
    assert logout_llamado == []


def test_es_login_true_y_se_cierra_sin_elegir_redirige_a_selector_perfil(app, db, monkeypatch):
    """`_volver_a_selector_perfil` debe limpiar la sesión con el método REAL
    `sesion_global.cerrar_sesion()` (nunca una asignación directa a `usuario_actual` — se saltaría
    el flush de stock/cierre de sesión de escritorio) y CERRAR esta ventana (`.close()`), nunca
    llamar a `detectar_logout()` directamente — esa llamada directa es justo el bug reproducido en
    producción (ver docstring del método): dejaba el `MenuPrincipal` vivo pero huérfano en el
    stack, y el SIGUIENTE login lo destruía con un `destroyed` tardío que `_procesar_retorno_o_cierre`
    interpretaba como "se cerró la ventana entera" y apagaba la app en mitad del 2º login."""
    monkeypatch.setattr("src.gui.migracion_gui.migracion_en_curso", lambda: False)
    monkeypatch.setattr("src.gui.selector_tienda.SelectorCentroDialog",
                        lambda *a, **k: _DialogoFalso(None))
    from src.db.usuario import sesion_global
    sesion_global.usuario_actual = {"id": "u1", "perfil": "SUPERADMIN", "nombre": "Test"}
    menu = _menu_stub()
    detectar_logout_llamado = []
    menu.detectar_logout = lambda: detectar_logout_llamado.append(1)
    cerrado = []
    menu.close = lambda: cerrado.append(1)   # instancia: sombrea QWidget.close para espiarlo
    try:
        menu._abrir_selector_centro(es_login=True)
        assert menu._recargado == []
        # Nunca se llama directamente — solo `.close()` + `destroyed` (en la app real) la disparan.
        assert detectar_logout_llamado == []
        assert cerrado == [1]                 # `.close()` sí se invocó de verdad
        assert menu._cerrando is True          # `_cerrar_recursos()` sí se ejecutó
        assert sesion_global.usuario_actual is None
    finally:
        sesion_global.usuario_actual = None


def test_es_login_false_y_se_cierra_sin_elegir_no_redirige(app, db, monkeypatch):
    """Reabierto a mano desde el chip (ya con sesión y centro resueltos): cerrarlo sin elegir no
    debe desloguear a nadie — comportamiento idéntico al de siempre."""
    monkeypatch.setattr("src.gui.migracion_gui.migracion_en_curso", lambda: False)
    monkeypatch.setattr("src.gui.selector_tienda.SelectorCentroDialog",
                        lambda *a, **k: _DialogoFalso(None))
    menu = _menu_stub()
    logout_llamado = []
    menu.detectar_logout = lambda: logout_llamado.append(1)
    menu._abrir_selector_centro()   # es_login=False por defecto
    assert menu._recargado == []
    assert logout_llamado == []


def test_migracion_en_curso_bloquea_igual_con_es_login(app, db, monkeypatch):
    import src.gui.menu_principal as menu_mod
    monkeypatch.setattr("src.gui.migracion_gui.migracion_en_curso", lambda: True)
    monkeypatch.setattr(menu_mod, "mostrar_mensaje", lambda *a, **k: None)  # evita el modal en headless
    llamadas = []
    monkeypatch.setattr("src.gui.selector_tienda.SelectorCentroDialog",
                        lambda *a, **k: llamadas.append(1))
    menu = _menu_stub()
    menu._abrir_selector_centro(es_login=True)
    assert llamadas == []
    assert menu._recargado == []
