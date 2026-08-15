"""Unificación de `id_tienda` a INT — grupo RRHH (migr 0195).

Empleados, jornadas y turnos: tienda concreta = int (central 'ALMC' → 0), sin tienda = NULL.
Verifica la coacción en las tres escrituras (empleados / control_horario / rrhh_pro).
"""

import datetime as dt

import pytest

from src.rrhh import control_horario as CH
from src.rrhh.db import empleados as EMP
from src.services.rrhh import rrhh_pro as PRO

pytestmark = pytest.mark.db


def _raw(db, tabla, campo, valor):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id_tienda FROM {tabla} WHERE {campo}=%s ORDER BY id DESC LIMIT 1", (valor,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else r["id_tienda"]) if r else "SIN_FILA"


def _limpia_emp(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def _nuevo_empleado(db, fab, id_empresa, id_tienda=None):
    eid = EMP.crear_empleado(id_empresa=id_empresa, nombre="Emp", nif="X" + str(id(fab))[-7:],
                             id_tienda=id_tienda)
    return eid


def test_empleado_id_tienda_int(db, fab):
    emp = fab.empresa("EMP rrhh A")
    fab.al_limpiar(lambda: _limpia_emp(db, emp))

    e_almc = EMP.crear_empleado(id_empresa=emp, nombre="A", nif="NIF-ALMC", id_tienda="ALMC")
    e_t2 = EMP.crear_empleado(id_empresa=emp, nombre="B", nif="NIF-T2", id_tienda=2)
    e_none = EMP.crear_empleado(id_empresa=emp, nombre="C", nif="NIF-NONE", id_tienda="")
    assert all([e_almc, e_t2, e_none])

    assert _raw(db, "rrhh_empleados", "id", e_almc) == 0     # 'ALMC' → 0
    assert _raw(db, "rrhh_empleados", "id", e_t2) == 2        # concreta → int
    assert _raw(db, "rrhh_empleados", "id", e_none) == 0      # '' → 0 (empleado siempre tiene tienda)


def test_jornada_id_tienda_int(db, fab):
    emp = fab.empresa("EMP rrhh B")
    fab.al_limpiar(lambda: _limpia_emp(db, emp))
    eid = EMP.crear_empleado(id_empresa=emp, nombre="J", nif="NIF-J")

    jid = CH.registrar_jornada(eid, dt.date(2026, 3, 2), "2026-03-02 09:00", "2026-03-02 17:00",
                               id_empresa=emp, id_tienda="ALMC")
    assert jid
    assert _raw(db, "rrhh_jornadas", "id", jid) == 0          # 'ALMC' → 0


def test_turno_id_tienda_int(db, fab):
    emp = fab.empresa("EMP rrhh C")
    fab.al_limpiar(lambda: _limpia_emp(db, emp))
    eid = EMP.crear_empleado(id_empresa=emp, nombre="T", nif="NIF-T")

    tid = PRO.planificar_turno(eid, "2026-03-03", hora_inicio="08:00", hora_fin="16:00",
                               id_tienda="ALMC", id_empresa=emp)
    assert tid
    assert _raw(db, "rrhh_turnos_plan", "id", tid) == 0       # 'ALMC' → 0
    # el cuadrante filtra por esa tienda (0 = central)
    filas = PRO.cuadrante("2026-03-01", "2026-03-31", id_tienda="ALMC", id_empresa=emp)
    assert any(f.get("id_empleado") == eid for f in filas)
