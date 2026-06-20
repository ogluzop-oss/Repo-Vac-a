"""
F4.10 · Portal del Empleado (autoconsulta, solo lectura).

Acceso por vínculo de usuario, visualización del panel propio (personal/contratos/
nóminas/vacaciones/ausencias/control horario/documentos), solicitud de vacaciones,
aislamiento multiempresa y seguridad (solo datos propios).
"""

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E
from src.rrhh import portal_servicio as PS
from src.rrhh.portal_servicio import AccesoDenegado


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _entorno(db, fab, id_usuario=5001, nif="64000001A"):
    emp = fab.empresa("F410")
    fab.al_limpiar(lambda: _limpia(db, emp))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", apellidos="Ruiz", nif=nif,
                           id_usuario=id_usuario, email="ana@x.com", puesto="Cajera")
    return emp, eid


# ── Acceso ────────────────────────────────────────────────────────────────────
def test_resolver_empleado_por_usuario(db, fab):
    emp, eid = _entorno(db, fab, id_usuario=5001)
    e = PS.resolver_empleado({"id": 5001, "nombre": "ana"}, emp)
    assert e and e["id"] == eid


def test_usuario_sin_vinculo_acceso_denegado(db, fab):
    emp, eid = _entorno(db, fab, id_usuario=5001)
    with pytest.raises(AccesoDenegado):
        PS.panel_de_usuario({"id": 9999, "nombre": "otro"}, emp)


# ── Panel propio ────────────────────────────────────────────────────────────
def test_panel_contiene_secciones(db, fab):
    from src.rrhh.db import contratos, nominas
    from src.rrhh import control_horario as CH, vacaciones_servicio as VS
    emp, eid = _entorno(db, fab)
    contratos.crear_contrato(eid, emp, modalidad="INDEFINIDO")
    nominas.crear_nomina(eid, emp, anio=2026, mes=6, bruto=2000, neto=1600, irpf_importe=300)
    VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    CH.registrar_jornada(eid, "2026-06-01", "2026-06-01 09:00", "2026-06-01 18:00",
                         planificada_min=480, id_empresa=emp)
    p = PS.panel(eid, emp)
    assert p["personal"]["nif"] == "64000001A" and p["personal"]["puesto"] == "Cajera"
    assert len(p["contratos"]) == 1 and len(p["nominas"]) == 1
    assert p["vacaciones"]["saldo"]["disponibles"] == 25      # 30 - 5 pendientes
    assert len(p["vacaciones"]["lista"]) == 1
    assert p["control_horario"]["totales"]["exceso_min"] == 60
    assert "documentos" in p


def test_panel_de_usuario(db, fab):
    emp, eid = _entorno(db, fab, id_usuario=5002, nif="64000002B")
    p = PS.panel_de_usuario({"id": 5002, "nombre": "ana"}, emp)
    assert p["personal"]["nif"] == "64000002B"


# ── Solicitud de vacaciones (delegada) ───────────────────────────────────────
def test_solicitar_vacaciones_desde_portal(db, fab):
    from src.rrhh import vacaciones_servicio as VS
    emp, eid = _entorno(db, fab)
    vid = PS.solicitar_vacaciones(eid, "2026-08-01", "2026-08-10", emp)
    assert vid
    assert len(VS.listar(eid, emp)) == 1


# ── Export control horario propio ────────────────────────────────────────────
def test_export_control_horario(db, fab):
    from src.rrhh import control_horario as CH
    emp, eid = _entorno(db, fab)
    CH.registrar_jornada(eid, "2026-06-02", "2026-06-02 09:00", "2026-06-02 17:00", id_empresa=emp)
    csv = PS.exportar_control_horario(eid, emp)
    assert "Fecha" in csv and "2026-06-02" in csv


# ── Seguridad: solo datos propios + multiempresa ─────────────────────────────
def test_aislamiento_entre_usuarios(db, fab):
    emp, e1 = _entorno(db, fab, id_usuario=5101, nif="64100001A")
    e2 = E.crear_empleado(id_empresa=emp, nombre="Leo", nif="64100002B", id_usuario=5102)
    # el usuario 5101 solo resuelve SU empleado, nunca el de 5102
    pa = PS.panel_de_usuario({"id": 5101}, emp)
    assert pa["personal"]["nif"] == "64100001A"
    assert PS.resolver_empleado({"id": 5101}, emp)["id"] == e1
    assert PS.resolver_empleado({"id": 5101}, emp)["id"] != e2


def test_aislamiento_multiempresa(db, fab):
    emp1, e1 = _entorno(db, fab, id_usuario=5201, nif="64200001A")
    emp2 = fab.empresa("F410 B"); fab.al_limpiar(lambda: _limpia(db, emp2))
    # mismo id_usuario en otra empresa no devuelve el empleado de emp1
    assert PS.resolver_empleado({"id": 5201}, emp2) is None


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_portal_gui_con_vinculo(db, fab, monkeypatch):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    emp, eid = _entorno(db, fab, id_usuario=5301, nif="64300001C")
    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.portal_empleado import PortalEmpleadoWindow
        w = PortalEmpleadoWindow(usuario={"id": 5301, "nombre": "ana", "perfil": "OPERARIO"})
        assert w.empleado is not None and w.empleado["id"] == eid
        w.close()


def test_portal_gui_sin_vinculo_no_rompe(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    emp, eid = _entorno(db, fab, id_usuario=5401, nif="64400001D")
    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.portal_empleado import PortalEmpleadoWindow
        w = PortalEmpleadoWindow(usuario={"id": 9998, "nombre": "x", "perfil": "OPERARIO"})
        assert w.empleado is None       # sin vínculo → aviso, sin error
        w.close()


# ── Menú ─────────────────────────────────────────────────────────────────────
def test_menu_incluye_portal(db):
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    sesion_global.usuario_actual = {"perfil": "OPERARIO", "nombre": "OP", "id": 1}
    try:
        menu = M.MenuPrincipal()
        assert "portal" in menu._cards        # visible incluso para OPERARIO
        menu.close()
    finally:
        sesion_global.usuario_actual = prev
    import inspect
    assert "PortalEmpleadoWindow" in inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
