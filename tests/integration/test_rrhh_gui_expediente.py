"""
F4.4 · GUI de expediente y gestión de empleados.

Verifica la ventana (listado/alta/edición), el visor de expediente y el FLUJO REAL
end-to-end: crear empleado (GUI) → generar documentos (wizard) → aparecen en el
expediente. Headless; modales neutralizados.
"""

import os

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E


@pytest.fixture(autouse=True)
def _sin_modales(monkeypatch):
    for m in ("warning", "information", "critical"):
        monkeypatch.setattr(f"src.gui.rrhh_gestion.QMessageBox.{m}",
                            lambda *a, **k: None, raising=False)


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _entorno(db, fab):
    from src.db import empresa as empmod
    emp = fab.empresa("F44")
    fab.al_limpiar(lambda: _limpia(db, emp))
    ctx = empmod.contexto_tenant(emp, None); ctx.__enter__()
    fab.al_limpiar(lambda: ctx.__exit__(None, None, None))
    return emp


# ── Ventana / listado ──────────────────────────────────────────────────────────
def test_ventana_abre_y_lista(db, fab):
    _app(); emp = _entorno(db, fab)
    E.crear_empleado(id_empresa=emp, nombre="Ana", apellidos="Ruiz", nif="10000000A", estado="activo")
    E.crear_empleado(id_empresa=emp, nombre="Leo", apellidos="Paz", nif="20000000B", estado="baja")
    from src.gui.rrhh_gestion import RRHHWindow
    w = RRHHWindow(usuario={"nombre": "T", "perfil": "ADMINISTRADOR"})
    assert w.tbl.rowCount() == 2
    # filtro por estado
    w.cb_filtro.setCurrentIndex([w.cb_filtro.itemData(i) for i in range(w.cb_filtro.count())].index("activo"))
    w._cargar()
    assert w.tbl.rowCount() == 1
    w.close()


# ── Alta vía formulario (lógica de guardado) ───────────────────────────────────
def test_alta_empleado_via_form(db, fab):
    _app(); emp = _entorno(db, fab)
    from src.gui.rrhh_gestion import EmpleadoFormDialog
    dlg = EmpleadoFormDialog(id_empresa=emp)
    dlg.in_nombre.setText("Eva"); dlg.in_apellidos.setText("Sanz")
    dlg.in_nif.setText("30000000c"); dlg.in_puesto.setText("Cajera")
    dlg.in_sal.setText("1300")
    dlg._guardar()
    assert dlg.resultado_id
    e = E.obtener_empleado(dlg.resultado_id, emp)
    assert e["nombre"] == "Eva" and e["nif"] == "30000000C" and e["puesto"] == "Cajera"


def test_alta_sin_nif_no_guarda(db, fab):
    _app(); emp = _entorno(db, fab)
    from src.gui.rrhh_gestion import EmpleadoFormDialog
    dlg = EmpleadoFormDialog(id_empresa=emp)
    dlg.in_nombre.setText("X")    # sin NIF
    dlg._guardar()
    assert dlg.resultado_id is None


def test_edicion_conserva_relaciones(db, fab):
    _app(); emp = _entorno(db, fab)
    from src.rrhh.db import contratos
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif="40000000D")
    contratos.crear_contrato(eid, emp, modalidad="INDEFINIDO")
    from src.gui.rrhh_gestion import EmpleadoFormDialog
    e = E.obtener_empleado(eid, emp)
    dlg = EmpleadoFormDialog(empleado=e, id_empresa=emp)
    dlg.in_puesto.setText("Encargada"); dlg._guardar()
    assert E.obtener_empleado(eid, emp)["puesto"] == "Encargada"
    assert len(contratos.listar_contratos(eid, emp)) == 1   # relación conservada


# ── Visor de expediente ────────────────────────────────────────────────────────
def test_visor_expediente(db, fab):
    _app(); emp = _entorno(db, fab)
    from src.rrhh.db import contratos, nominas, vacaciones, ausencias, documentos
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif="50000000E")
    contratos.crear_contrato(eid, emp, modalidad="TEMPORAL")
    nominas.crear_nomina(eid, emp, anio=2026, mes=6, bruto=2000, neto=1600)
    vacaciones.crear_vacaciones(eid, emp, anio=2026, dias=5)
    ausencias.crear_ausencia(eid, emp, tipo="permiso")
    documentos.crear_documento(eid, emp, tipo_doc="contrato", ref_documento="x.pdf",
                               datos_snapshot='{"nif":"50000000E"}')
    from src.gui.rrhh_gestion import ExpedienteDialog
    dlg = ExpedienteDialog(eid, emp)
    assert dlg.exp["empleado"]["id"] == eid
    assert len(dlg.exp["contratos"]) == 1 and len(dlg.exp["nominas"]) == 1
    assert len(dlg.exp["documentos"]) == 1
    assert dlg.tbl_docs.rowCount() == 1
    dlg.close()


# ── Flujo real end-to-end (Fase 7) ─────────────────────────────────────────────
def test_flujo_completo_gui(db, fab):
    """Crear empleado (GUI) → generar CONTRATO y NÓMINA (wizard) → aparecen en expediente."""
    _app(); emp = _entorno(db, fab)
    NIF = "60000000F"
    # 1. Alta de empleado desde la GUI
    from src.gui.rrhh_gestion import EmpleadoFormDialog
    dlg = EmpleadoFormDialog(id_empresa=emp)
    dlg.in_nombre.setText("Marta"); dlg.in_nif.setText(NIF); dlg.in_sal.setText("2000")
    dlg._guardar()
    eid = dlg.resultado_id
    assert eid
    # 2/3. Generar documentos con ese NIF (wizard → hook de persistencia F4.2.1)
    import src.gui.gestion_usuarios as gu
    pdfs = []
    for tipo, datos in [
        ("CONTRATO", dict(trabajador="Marta", nif=NIF, fecha="10/06/2026", subtipo="INDEFINIDO",
                          salario="2000", fecha_fin="31/12/2026")),
        ("NÓMINA", dict(trabajador="Marta", nif=NIF, fecha="30/06/2026", salario="2000",
                        num_pagas="14", irpf_pct="15", grupo_cotizacion="1")),
    ]:
        w = gu._WizardDocumentoFiscal(); w._tipo = tipo; w._datos = dict(datos)
        w._generar_pdf()
        if getattr(w, "_pdf_ruta", None):
            pdfs.append(w._pdf_ruta)
    for r in pdfs:
        fab.al_limpiar(lambda x=r: os.path.exists(x) and os.remove(x))
    # 4-7. El expediente refleja contrato + nómina + documentos
    exp = E.expediente(eid, emp)
    assert len(exp["contratos"]) == 1 and exp["contratos"][0]["modalidad"] == "INDEFINIDO"
    assert len(exp["nominas"]) == 1 and float(exp["nominas"][0]["bruto"]) > 0
    assert len(exp["documentos"]) >= 2     # contrato + nómina vinculados


# ── Menú: tarjeta + routing ────────────────────────────────────────────────────
def test_menu_incluye_rrhh(db):
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    sesion_global.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
    try:
        menu = M.MenuPrincipal()
        assert "rrhh" in menu._cards
        menu.close()
    finally:
        sesion_global.usuario_actual = prev
    import inspect
    assert "RRHHWindow" in inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
