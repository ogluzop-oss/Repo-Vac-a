"""
`_BloqueadosDialog` (gui.contabilidad_gestion) — superficie de revisión manual para los eventos de
la cola contable bloqueados por ejercicio cerrado (ver `services.contabilidad.posting.
_separar_bloqueados_por_cierre`). Antes de esto no había ninguna forma de ver ni actuar sobre
estos eventos — se reintentaban en silencio para siempre en cada arranque de la app.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _sin_popups_bloqueantes(monkeypatch):
    """`_aviso()` abre un `QMessageBox`-estilo propio con `.exec()` (MODAL, bloqueante) — en un
    test headless, sin nadie que lo cierre, cuelga el proceso para siempre (no un fallo rápido).
    Se sustituye por un registro en memoria: no cambia la lógica bajo prueba (`_reintentar()`
    sigue ejecutando exactamente lo mismo), solo evita la ventana real."""
    import src.gui.contabilidad_gestion as mod
    llamadas = []
    monkeypatch.setattr(mod, "_aviso", lambda *a, **k: llamadas.append((a, k)))
    return llamadas


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


@pytest.fixture
def entorno_bloqueado(db, fab):
    from src.db.empresa import empresa_actual_id, set_empresa_actual, EMPRESA_DEFAULT_ID
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("GUI CONTAB BLOQ")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, 2026)
    assert K.cerrar_ejercicio(2026, emp)
    Pg.encolar_venta("vguibloq", 121.0, "2026-05-10", "efectivo", id_empresa=emp)
    previa = empresa_actual_id()
    set_empresa_actual(emp)
    try:
        Pg.procesar_cola(emp)
        yield emp
    finally:
        set_empresa_actual(previa or EMPRESA_DEFAULT_ID)


def test_dialogo_lista_el_evento_bloqueado(app, entorno_bloqueado):
    from src.gui.contabilidad_gestion import _BloqueadosDialog
    dlg = _BloqueadosDialog()
    try:
        assert dlg.tbl.rowCount() == 1
        assert dlg.tbl.item(0, 2).text() == "vguibloq"
        assert "cerrado" in dlg.tbl.item(0, 3).text()
    finally:
        dlg.deleteLater()


def test_reintentar_sin_reabrir_el_ejercicio_lo_marca_pendiente_pero_sigue_sin_poder_contabilizarse(
        app, entorno_bloqueado):
    """El diálogo solo re-encola (vuelve a 'pendiente'); si el ejercicio SIGUE cerrado, el
    siguiente `procesar_cola()` lo volverá a bloquear — no debe crear un asiento imposible."""
    from src.services.contabilidad import posting as Pg
    from src.gui.contabilidad_gestion import _BloqueadosDialog
    emp = entorno_bloqueado
    dlg = _BloqueadosDialog()
    try:
        dlg.tbl.selectRow(0)
        dlg._reintentar()
        assert dlg.tbl.rowCount() == 0, "tras reintentar, ya no debe listarse como bloqueado"

        res = Pg.procesar_cola(emp)
        assert res["bloqueados"] == 1, "el ejercicio sigue cerrado: vuelve a bloquearse, no se pierde"
    finally:
        dlg.deleteLater()


def test_reintentar_tras_reabrir_el_ejercicio_permite_contabilizar(app, entorno_bloqueado):
    from src.services.contabilidad import cuentas as K, posting as Pg
    from src.gui.contabilidad_gestion import _BloqueadosDialog
    emp = entorno_bloqueado
    assert K.reabrir_ejercicio(2026, emp)
    dlg = _BloqueadosDialog()
    try:
        dlg.tbl.selectRow(0)
        dlg._reintentar()
        res = Pg.procesar_cola(emp)
        assert res["ventas"] == 1
        assert Pg.listar_bloqueados_por_cierre(emp) == []
    finally:
        dlg.deleteLater()
