"""
Delegación a SOMA — GUI (`gui.soma_delegacion_gui`). Offscreen (QT_QPA_PLATFORM=offscreen, fijado
en conftest) + BD real: el diálogo de alta NUNCA se puede aceptar sin instrucciones (el encargo
exige que el SUPERADMIN SIEMPRE defina cómo debe proceder SOMA). `DelegacionSomaPanel` es el
panel REUTILIZABLE embebido como pestaña "Delegación IA" en cada módulo (no hay ventana/tarjeta
de menú propia) — aquí se prueba filtrando por `pantalla`, igual que lo haría cada ventana real.
"""

import pytest

from src.gui.soma_delegacion_gui import DelegacionSomaPanel, _ReglaDialog
from src.services.soma_delegacion import catalogo as CAT
from src.services.soma_delegacion import reglas as R

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM soma_delegaciones_historial WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM soma_delegaciones WHERE id_empresa=%s", (emp,))
        conn.commit()


def _tipos_correo():
    return [t for t in CAT.listar() if t["pantalla"] == "correo"]


def test_dialogo_no_acepta_sin_instrucciones():
    d = _ReglaDialog(tipos=_tipos_correo())
    d.txt_instrucciones.setPlainText("")
    d._intentar_aceptar()
    assert d.result() != d.DialogCode.Accepted
    assert "cómo debe proceder" in d.lbl_error.text()


def test_dialogo_acepta_con_instrucciones():
    d = _ReglaDialog(tipos=_tipos_correo())
    d.txt_instrucciones.setPlainText("Responde solo a preguntas de horario.")
    d._intentar_aceptar()
    assert d.result() == d.DialogCode.Accepted
    datos = d.datos()
    assert datos["instrucciones"] == "Responde solo a preguntas de horario."
    assert datos["tipo"] == "correo.responder_automatico"


def test_dialogo_editar_regla_precarga_datos(emp):
    rid = R.crear_regla("correo.responder_automatico", "Instrucciones originales.",
                        modo_aplicacion="automatico", id_empresa=emp)
    regla = R.obtener_regla(rid, id_empresa=emp)
    d = _ReglaDialog(tipos=_tipos_correo(), regla=regla)
    assert d.txt_instrucciones.toPlainText() == "Instrucciones originales."
    assert not d.cmb_tipo.isEnabled()   # el tipo no se cambia al editar


def test_panel_filtra_por_pantalla(emp):
    R.crear_regla("correo.responder_automatico", "Regla de correo.", id_empresa=emp)
    R.crear_regla("crm.generar_presupuesto", "Regla de CRM.", id_empresa=emp)
    panel_correo = DelegacionSomaPanel(pantalla="correo", usuario={"id": 1, "perfil": "SUPERADMIN"})
    assert panel_correo.tbl_reglas.rowCount() == 1
    panel_crm = DelegacionSomaPanel(pantalla="crm", usuario={"id": 1, "perfil": "SUPERADMIN"})
    assert panel_crm.tbl_reglas.rowCount() == 1


def test_panel_crm_muestra_presupuesto_y_autorrelleno_cliente_juntos(emp):
    R.crear_regla("crm.generar_presupuesto", "x", id_empresa=emp)
    R.crear_regla("configuracion.autorrelleno_cliente", "x", id_empresa=emp)
    panel = DelegacionSomaPanel(pantalla="crm", usuario={"id": 1, "perfil": "SUPERADMIN"})
    assert panel.tbl_reglas.rowCount() == 2


def test_panel_lista_reglas_y_se_actualiza(emp):
    w = DelegacionSomaPanel(pantalla="correo", usuario={"id": 1, "perfil": "SUPERADMIN"})
    assert w.tbl_reglas.rowCount() == 0
    R.crear_regla("correo.responder_automatico", "Responde a horarios.", id_empresa=emp)
    w._cargar_reglas()
    assert w.tbl_reglas.rowCount() == 1


def test_panel_alternar_regla_sin_seleccion_no_lanza(emp):
    w = DelegacionSomaPanel(pantalla="correo", usuario={"id": 1, "perfil": "SUPERADMIN"})
    w._alternar_regla()   # nada seleccionado -> debe avisar, nunca lanzar
    w._editar_regla()
    w._eliminar_regla()


def test_panel_historial_vacio_no_lanza(emp):
    w = DelegacionSomaPanel(pantalla="correo", usuario={"id": 1, "perfil": "SUPERADMIN"})
    assert w.tbl_historial.rowCount() == 0
    w._aplicar_pendiente()
    w._descartar_pendiente()
