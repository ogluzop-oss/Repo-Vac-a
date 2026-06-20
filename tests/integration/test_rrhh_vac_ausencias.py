"""
F4.7 · Gestión operativa de vacaciones y ausencias.

Saldo, solicitud, aprobación/denegación/cancelación, alta/edición de ausencias,
validaciones (fechas, días, solapamientos), calendario, integración con el expediente,
multiempresa y GUI (dialog).
"""

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E
from src.rrhh import ausencias_servicio as AS
from src.rrhh import vacaciones_servicio as VS
from src.rrhh.vacaciones_servicio import GestionLaboralError


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _emp(db, fab, nif="70000000A"):
    emp = fab.empresa("F47")
    fab.al_limpiar(lambda: _limpia(db, emp))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif=nif)
    return emp, eid


# ── Saldo ──────────────────────────────────────────────────────────────────────
def test_saldo_inicial(db, fab):
    emp, eid = _emp(db, fab)
    s = VS.saldo(eid, anio=2026, id_empresa=emp)
    assert s["asignados"] == 30 and s["disfrutados"] == 0 and s["disponibles"] == 30


def test_saldo_descuenta_aprobadas_y_pendientes(db, fab):
    emp, eid = _emp(db, fab)
    v1 = VS.solicitar(eid, "2026-07-01", "2026-07-10", id_empresa=emp)   # 10 días pendiente
    VS.solicitar(eid, "2026-08-01", "2026-08-05", id_empresa=emp)        # 5 días pendiente
    VS.aprobar(v1, usuario="Jefe", id_empresa=emp)                        # 10 aprobados
    s = VS.saldo(eid, anio=2026, id_empresa=emp)
    assert s["disfrutados"] == 10 and s["pendientes"] == 5 and s["disponibles"] == 15


# ── Solicitud + ciclo de estados ───────────────────────────────────────────────
def test_solicitar_calcula_dias(db, fab):
    emp, eid = _emp(db, fab)
    vid = VS.solicitar(eid, "2026-07-01", "2026-07-07", id_empresa=emp)
    v = VS.listar(eid, emp)[0]
    assert v["id"] == vid and float(v["dias"]) == 7.0 and v["estado"] == "pendiente"


def test_aprobar_denegar_cancelar(db, fab):
    emp, eid = _emp(db, fab)
    a = VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    assert VS.aprobar(a, usuario="J", id_empresa=emp)
    b = VS.solicitar(eid, "2026-09-01", "2026-09-03", id_empresa=emp)
    assert VS.denegar(b, id_empresa=emp)
    c = VS.solicitar(eid, "2026-10-01", "2026-10-02", id_empresa=emp)
    assert VS.cancelar(c, id_empresa=emp)
    estados = {v["id"]: v["estado"] for v in VS.listar(eid, emp)}
    assert estados[a] == "aprobada" and estados[b] == "denegada" and estados[c] == "cancelada"


def test_no_aprobar_si_no_pendiente(db, fab):
    emp, eid = _emp(db, fab)
    a = VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    VS.aprobar(a, id_empresa=emp)
    with pytest.raises(GestionLaboralError):
        VS.aprobar(a, id_empresa=emp)        # ya aprobada


# ── Validaciones ────────────────────────────────────────────────────────────────
def test_fechas_invertidas(db, fab):
    emp, eid = _emp(db, fab)
    with pytest.raises(GestionLaboralError):
        VS.solicitar(eid, "2026-07-10", "2026-07-01", id_empresa=emp)


def test_solapamiento_vacaciones(db, fab):
    emp, eid = _emp(db, fab)
    VS.solicitar(eid, "2026-07-01", "2026-07-10", id_empresa=emp)
    with pytest.raises(GestionLaboralError, match="solap"):
        VS.solicitar(eid, "2026-07-05", "2026-07-15", id_empresa=emp)


def test_solapamiento_no_bloquea_si_denegada(db, fab):
    emp, eid = _emp(db, fab)
    a = VS.solicitar(eid, "2026-07-01", "2026-07-10", id_empresa=emp)
    VS.denegar(a, id_empresa=emp)
    # denegada no cuenta → se puede solicitar en las mismas fechas
    assert VS.solicitar(eid, "2026-07-05", "2026-07-15", id_empresa=emp)


# ── Ausencias ────────────────────────────────────────────────────────────────
def test_registrar_ausencia(db, fab):
    emp, eid = _emp(db, fab)
    aid = AS.registrar(eid, "enfermedad", "2026-03-01", "2026-03-05", motivo="gripe",
                       justificada=True, id_empresa=emp)
    a = AS.listar(eid, emp)[0]
    assert a["id"] == aid and a["tipo"] == "enfermedad" and float(a["dias"]) == 5.0


def test_tipo_ausencia_invalido(db, fab):
    emp, eid = _emp(db, fab)
    with pytest.raises(GestionLaboralError):
        AS.registrar(eid, "vacaciones_raras", "2026-03-01", "2026-03-02", id_empresa=emp)


def test_ausencias_solapadas(db, fab):
    emp, eid = _emp(db, fab)
    AS.registrar(eid, "permiso_ret", "2026-03-01", "2026-03-05", id_empresa=emp)
    with pytest.raises(GestionLaboralError, match="solap"):
        AS.registrar(eid, "enfermedad", "2026-03-04", "2026-03-08", id_empresa=emp)


def test_editar_ausencia(db, fab):
    emp, eid = _emp(db, fab)
    aid = AS.registrar(eid, "otros", "2026-03-01", "2026-03-02", id_empresa=emp)
    assert AS.editar(aid, emp, motivo="actualizado", fecha_fin="2026-03-04")
    a = AS.listar(eid, emp)[0]
    assert a["motivo"] == "actualizado" and float(a["dias"]) == 4.0


# ── Calendario + expediente ──────────────────────────────────────────────────
def test_calendario_combina_vac_aprobadas_y_ausencias(db, fab):
    emp, eid = _emp(db, fab)
    v = VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    VS.aprobar(v, id_empresa=emp)
    VS.solicitar(eid, "2026-08-01", "2026-08-03", id_empresa=emp)      # pendiente → NO en calendario
    AS.registrar(eid, "enfermedad", "2026-03-01", "2026-03-02", id_empresa=emp)
    cal = AS.calendario(eid, emp)
    tipos = [e["tipo"] for e in cal]
    assert "Vacaciones" in tipos and any("Enfermedad" in t for t in tipos)
    assert len(cal) == 2                       # la pendiente no aparece


def test_integracion_expediente(db, fab):
    emp, eid = _emp(db, fab)
    VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    AS.registrar(eid, "permiso_ret", "2026-03-01", "2026-03-02", id_empresa=emp)
    exp = E.expediente(eid, emp)
    assert len(exp["vacaciones"]) == 1 and len(exp["ausencias"]) == 1


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_multiempresa(db, fab):
    emp1, e1 = _emp(db, fab, nif="71000000A")
    emp2 = fab.empresa("F47 B"); fab.al_limpiar(lambda: _limpia(db, emp2))
    e2 = E.crear_empleado(id_empresa=emp2, nombre="Leo", nif="72000000B")
    VS.solicitar(e1, "2026-07-01", "2026-07-05", id_empresa=emp1)
    assert len(VS.listar(e1, emp1)) == 1
    assert len(VS.listar(e2, emp2)) == 0       # aislado


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_gui_dialog_construye_y_refresca(db, fab, monkeypatch):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    for m in ("warning", "information"):
        monkeypatch.setattr(f"src.gui.rrhh_gestion.QMessageBox.{m}", lambda *a, **k: None, raising=False)
    emp, eid = _emp(db, fab, nif="73000000C")
    VS.solicitar(eid, "2026-07-01", "2026-07-05", id_empresa=emp)
    from src.gui.rrhh_gestion import GestionLaboralDialog
    dlg = GestionLaboralDialog(eid, emp)
    assert dlg.tbl_vac.rowCount() == 1
    assert "asignados 30" in dlg.lbl_saldo.text()
    dlg.close()
