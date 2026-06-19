"""E6.7 · Ventana de Contabilidad: apertura, navegación, datos, cierre, menú."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _sin_modales(monkeypatch):
    """Neutraliza los diálogos modales (bloquean en headless)."""
    monkeypatch.setattr("src.gui.contabilidad_gestion.mostrar_mensaje",
                        lambda *a, **k: None, raising=False)


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("contab_asientos", "contab_cola", "contab_cuentas",
                  "contab_ejercicios", "contab_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_ventana_abre_y_secciones(db, fab):
    from src.db.empresa import contexto_tenant
    from src.gui.contabilidad_gestion import ContabilidadWindow
    emp = fab.empresa("CGUI ABRE")
    fab.al_limpiar(lambda: _borra(db, emp))
    with contexto_tenant(emp, None):
        from src.services.contabilidad import cuentas as K
        K.activar(emp, 2026)
        w = ContabilidadWindow(callback_vuelta=lambda: None, usuario={"nombre": "T"})
        assert w.stack.count() == 6
        for i in range(6):
            w._ir(i); assert w.stack.currentIndex() == i
        w.close()


def test_carga_datos_contables(db, fab):
    from src.db.empresa import contexto_tenant
    from src.gui.contabilidad_gestion import ContabilidadWindow
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("CGUI DATOS")
    fab.al_limpiar(lambda: _borra(db, emp))
    with contexto_tenant(emp, None):
        K.activar(emp, 2026)
        Pg.encolar_venta("v1", 121.0, "2026-08-01", "efectivo", id_empresa=emp)
        Pg.procesar_cola(emp)
        w = ContabilidadWindow(usuario={"nombre": "T"})
        w._load_plan(); assert w.tbl_plan.rowCount() > 0          # plan cargado
        w._load_diario(); assert w.tbl_diario.rowCount() == 1     # 1 asiento
        w._load_balances(); assert "cuadra" in w.lbl_bal.text()
        w.in_mayor_cta.setText("700"); w._load_mayor()
        assert w.tbl_mayor.rowCount() == 1
        w._load_iva("repercutido"); assert "cuota 21.0" in w.lbl_iva.text()
        w.close()


def test_cierre_ejercicio_desde_gui(db, fab):
    from src.db.empresa import contexto_tenant
    from src.gui.contabilidad_gestion import ContabilidadWindow
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CGUI CIERRE")
    fab.al_limpiar(lambda: _borra(db, emp))
    with contexto_tenant(emp, None):
        K.activar(emp, 2026)
        w = ContabilidadWindow(usuario={"nombre": "T"})
        w._cerrar()
        assert K.ejercicio_cerrado(2026, emp) is True
        w.close()


def test_menu_incluye_contabilidad(db):
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    sesion_global.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    try:
        menu = M.MenuPrincipal()
        assert "contabilidad" in menu._cards
        menu.close()
    finally:
        sesion_global.usuario_actual = prev
    import inspect
    assert "ContabilidadWindow" in inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
