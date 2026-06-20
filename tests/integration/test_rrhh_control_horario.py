"""
F4.9 · Control horario laboral (RD 8/2019).

Registro diario, pausas descontadas, exceso/déficit, validaciones, alertas, informes
(diario/mensual/anual), exportación (CSV/Excel), puente desde fichajes, integración con
el expediente, multiempresa y multitienda. GUI dialog.
"""

import os

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E
from src.rrhh import control_horario as CH
from src.rrhh.control_horario import ControlHorarioError


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))   # cascada jornadas/pausas
        cur.execute("DELETE FROM fichajes WHERE usuario_id IN (991001, 991002)")
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _emp(db, fab, nif="60000001A"):
    emp = fab.empresa("F49")
    fab.al_limpiar(lambda: _limpia(db, emp))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif=nif)
    return emp, eid


# ── Cálculo ──────────────────────────────────────────────────────────────────
def test_jornada_normal(db, fab):
    emp, eid = _emp(db, fab)
    jid = CH.registrar_jornada(eid, "2026-06-01", "2026-06-01 09:00", "2026-06-01 17:00",
                               planificada_min=480, id_empresa=emp)
    j = CH.obtener_jornada(jid, emp)
    assert j["tiempo_efectivo_min"] == 480 and j["exceso_min"] == 0 and j["deficit_min"] == 0


def test_pausas_descontadas(db, fab):
    emp, eid = _emp(db, fab)
    jid = CH.registrar_jornada(eid, "2026-06-02", "2026-06-02 09:00", "2026-06-02 18:00",
                               pausas=[{"tipo": "comida", "inicio": "2026-06-02 13:00",
                                        "fin": "2026-06-02 14:00"}],
                               planificada_min=480, id_empresa=emp)
    j = CH.obtener_jornada(jid, emp)
    assert j["pausa_segundos"] == 3600 and j["tiempo_efectivo_min"] == 480   # 9h - 1h
    assert len(j["pausas"]) == 1 and j["pausas"][0]["tipo"] == "comida"


def test_exceso_y_deficit(db, fab):
    emp, eid = _emp(db, fab)
    j1 = CH.obtener_jornada(CH.registrar_jornada(eid, "2026-06-03", "2026-06-03 09:00",
                            "2026-06-03 19:00", planificada_min=480, id_empresa=emp), emp)
    assert j1["exceso_min"] == 120 and j1["deficit_min"] == 0
    j2 = CH.obtener_jornada(CH.registrar_jornada(eid, "2026-06-04", "2026-06-04 09:00",
                            "2026-06-04 13:00", planificada_min=480, id_empresa=emp), emp)
    assert j2["deficit_min"] == 240 and j2["exceso_min"] == 0


# ── Validaciones ──────────────────────────────────────────────────────────────
def test_salida_anterior_entrada(db, fab):
    emp, eid = _emp(db, fab)
    with pytest.raises(ControlHorarioError):
        CH.registrar_jornada(eid, "2026-06-05", "2026-06-05 18:00", "2026-06-05 09:00",
                             id_empresa=emp)


def test_jornada_duplicada(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-06", "2026-06-06 09:00", "2026-06-06 17:00", id_empresa=emp)
    with pytest.raises(ControlHorarioError, match="Ya existe"):
        CH.registrar_jornada(eid, "2026-06-06", "2026-06-06 10:00", "2026-06-06 18:00", id_empresa=emp)


def test_pausa_tipo_invalido(db, fab):
    emp, eid = _emp(db, fab)
    with pytest.raises(ControlHorarioError):
        CH.registrar_jornada(eid, "2026-06-07", "2026-06-07 09:00", "2026-06-07 17:00",
                             pausas=[{"tipo": "siesta", "inicio": "2026-06-07 13:00",
                                      "fin": "2026-06-07 14:00"}], id_empresa=emp)


# ── Alertas ──────────────────────────────────────────────────────────────────
def test_alertas(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-08", "2026-06-08 09:00", None, id_empresa=emp)   # incompleta
    CH.registrar_jornada(eid, "2026-06-09", "2026-06-09 09:00", "2026-06-09 20:00",
                         planificada_min=480, id_empresa=emp)                            # exceso
    inc = CH.alertas(eid, emp)
    tipos = {i["tipo"] for i in inc}
    assert "jornada_incompleta" in tipos and "exceso_jornada" in tipos


# ── Informes ──────────────────────────────────────────────────────────────────
def test_informe_mensual_y_totales(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-01", "2026-06-01 09:00", "2026-06-01 17:00",
                         planificada_min=480, id_empresa=emp)
    CH.registrar_jornada(eid, "2026-06-02", "2026-06-02 09:00", "2026-06-02 18:00",
                         planificada_min=480, id_empresa=emp)
    inf = CH.informe_mensual(eid, 2026, 6, emp)
    assert inf["totales"]["dias"] == 2
    assert inf["totales"]["efectivo_min"] == 480 + 540
    assert inf["totales"]["exceso_min"] == 60
    # anual incluye junio
    assert CH.informe_anual(eid, 2026, emp)["totales"]["dias"] == 2
    # diario
    assert CH.informe_diario(eid, "2026-06-01", emp)["totales"]["dias"] == 1


# ── Exportaciones ──────────────────────────────────────────────────────────────
def test_export_csv(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-10", "2026-06-10 09:00", "2026-06-10 17:00", id_empresa=emp)
    csv = CH.exportar_csv(CH.listar_jornadas(eid, emp))
    assert "Fecha" in csv and "Efectivo (min)" in csv and "2026-06-10" in csv


def test_export_excel(db, fab, tmp_path):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-11", "2026-06-11 09:00", "2026-06-11 17:00", id_empresa=emp)
    ruta = str(tmp_path / "ch.xlsx")
    r = CH.exportar_excel(CH.listar_jornadas(eid, emp), ruta)
    if r is None:
        pytest.skip("openpyxl no disponible")
    assert os.path.exists(ruta) and os.path.getsize(ruta) > 0


# ── Puente fichajes ─────────────────────────────────────────────────────────
def test_importar_de_fichajes(db, fab):
    emp, eid = _emp(db, fab)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO fichajes (usuario_id, nombre_empleado, entrada, salida) "
                    "VALUES (991001,'Ana','2026-05-02 08:00:00','2026-05-02 16:00:00')")
        conn.commit()
    n = CH.importar_de_fichajes(eid, 991001, id_empresa=emp)
    assert n == 1
    j = CH.listar_jornadas(eid, emp, desde="2026-05-01", hasta="2026-05-31")
    assert len(j) == 1 and j[0]["origen"] == "fichaje" and j[0]["tiempo_efectivo_min"] == 480


# ── Expediente + multiempresa/multitienda ────────────────────────────────────
def test_expediente_incluye_control_horario(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-12", "2026-06-12 09:00", "2026-06-12 17:00", id_empresa=emp)
    exp = E.expediente(eid, emp)
    assert "control_horario" in exp and len(exp["control_horario"]) == 1


def test_multitienda_filtro(db, fab):
    emp, eid = _emp(db, fab)
    CH.registrar_jornada(eid, "2026-06-13", "2026-06-13 09:00", "2026-06-13 17:00",
                         id_empresa=emp, id_tienda="T1")
    CH.registrar_jornada(eid, "2026-06-14", "2026-06-14 09:00", "2026-06-14 17:00",
                         id_empresa=emp, id_tienda="T2")
    assert len(CH.listar_jornadas(eid, emp, id_tienda="T1")) == 1
    assert len(CH.listar_jornadas(eid, emp)) == 2


def test_multiempresa(db, fab):
    emp1, e1 = _emp(db, fab, nif="61000001A")
    emp2 = fab.empresa("F49 B"); fab.al_limpiar(lambda: _limpia(db, emp2))
    e2 = E.crear_empleado(id_empresa=emp2, nombre="Leo", nif="62000001B")
    CH.registrar_jornada(e1, "2026-06-15", "2026-06-15 09:00", "2026-06-15 17:00", id_empresa=emp1)
    assert len(CH.listar_jornadas(e1, emp1)) == 1
    assert len(CH.listar_jornadas(e2, emp2)) == 0


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_gui_control_horario(db, fab, monkeypatch):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    for m in ("warning", "information"):
        monkeypatch.setattr(f"src.gui.rrhh_gestion.QMessageBox.{m}", lambda *a, **k: None, raising=False)
    emp, eid = _emp(db, fab, nif="63000001C")
    CH.registrar_jornada(eid, "2026-06-16", "2026-06-16 09:00", "2026-06-16 17:00", id_empresa=emp)
    from src.gui.rrhh_gestion import ControlHorarioDialog
    dlg = ControlHorarioDialog(eid, emp)
    assert dlg.tbl.rowCount() == 1
    assert "efectivo 480" in dlg.lbl_tot.text()
    dlg.close()
