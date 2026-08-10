"""
Tests de GESTIÓN DE PROYECTOS (migración 0172): CRUD de proyecto, tablero Kanban (crear/mover tareas),
cronograma (Gantt por fechas), imputación de horas/costes, rentabilidad (presupuesto − coste real),
eliminación en cascada y aislamiento multiempresa.
"""

import pytest

from src.services.proyectos import proyectos as P
from src.services.proyectos import seguimiento as S
from src.services.proyectos import tareas as T


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _proyecto(fab, emp, **kw):
    pid = P.crear_proyecto(kw.pop("nombre", "Proyecto Test"), id_empresa=emp, **kw)
    for t in ("proyecto_costes", "proyecto_horas", "proyecto_tareas"):
        fab._borrar(t, "id_proyecto", pid)
    fab._borrar("proyectos", "id", pid)
    return pid


def test_crud_proyecto(fab, emp):
    pid = _proyecto(fab, emp, presupuesto=1000)
    assert pid
    assert any(p["id"] == pid for p in P.listar_proyectos(id_empresa=emp))
    assert P.actualizar_proyecto(pid, id_empresa=emp, estado="en_curso", presupuesto=2000)
    p = P.obtener_proyecto(pid, id_empresa=emp)
    assert p["estado"] == "en_curso" and float(p["presupuesto"]) == 2000


def test_kanban_crear_y_mover(fab, emp):
    pid = _proyecto(fab, emp)
    t1 = T.crear_tarea(pid, "Diseño", id_empresa=emp)
    t2 = T.crear_tarea(pid, "Backend", id_empresa=emp)
    tab = T.tablero(pid, id_empresa=emp)
    assert [t["id"] for t in tab["pendiente"]] == [t1, t2]        # ambas en pendiente, en orden
    assert [t["orden"] for t in tab["pendiente"]] == [0, 1]
    assert T.mover_tarea(t1, "en_curso", id_empresa=emp)
    tab = T.tablero(pid, id_empresa=emp)
    assert len(tab["pendiente"]) == 1 and len(tab["en_curso"]) == 1
    # mover a columna inválida no hace nada
    assert T.mover_tarea(t1, "columna_inexistente", id_empresa=emp) is False


def test_cronograma_solo_con_fechas(fab, emp):
    pid = _proyecto(fab, emp)
    T.crear_tarea(pid, "Sin fecha", id_empresa=emp)
    tf = T.crear_tarea(pid, "Con fecha", fecha_inicio="2026-07-01", fecha_fin="2026-07-05", id_empresa=emp)
    cr = T.cronograma(pid, id_empresa=emp)
    assert len(cr) == 1 and cr[0]["id"] == tf


def test_horas_costes_rentabilidad(fab, emp):
    pid = _proyecto(fab, emp, presupuesto=10000, coste_hora_defecto=40)
    S.registrar_horas(pid, 10, id_empresa=emp)                 # 10×40 = 400 (coste por defecto)
    S.registrar_horas(pid, 5, coste_hora=60, id_empresa=emp)   # 5×60  = 300
    S.registrar_coste(pid, "Licencias", 300, id_empresa=emp)
    r = S.rentabilidad(pid, id_empresa=emp)
    assert r["horas_totales"] == 15
    assert r["coste_horas"] == 700 and r["coste_extra"] == 300 and r["coste_total"] == 1000
    assert r["margen"] == 9000 and r["margen_pct"] == 90.0
    # horas no positivas se rechazan
    assert S.registrar_horas(pid, 0, id_empresa=emp) is None


def test_eliminar_cascada(fab, emp):
    pid = _proyecto(fab, emp)
    T.crear_tarea(pid, "T", id_empresa=emp)
    S.registrar_horas(pid, 3, id_empresa=emp)
    S.registrar_coste(pid, "C", 10, id_empresa=emp)
    assert P.eliminar_proyecto(pid, id_empresa=emp)
    assert P.obtener_proyecto(pid, id_empresa=emp) is None
    assert T.listar_tareas(pid, id_empresa=emp) == []
    assert S.listar_horas(pid, id_empresa=emp) == [] and S.listar_costes(pid, id_empresa=emp) == []


def test_aislamiento_empresa(fab, emp):
    otra = fab.empresa("EMPRESA PROY B")
    pa = _proyecto(fab, emp, nombre="Solo A")
    pb = P.crear_proyecto("Solo B", id_empresa=otra)
    fab._borrar("proyectos", "id", pb)
    ids_a = {p["id"] for p in P.listar_proyectos(id_empresa=emp)}
    ids_b = {p["id"] for p in P.listar_proyectos(id_empresa=otra)}
    assert pa in ids_a and pa not in ids_b
    assert pb in ids_b and pb not in ids_a
    assert P.obtener_proyecto(pb, id_empresa=emp) is None       # no cruza empresas
