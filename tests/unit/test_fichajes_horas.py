"""
Tests · Fichajes · Horas trabajadas por empleado del mes en curso.

Verifica `usuario.horas_mes_por_empleado`: suma la duración de los fichajes del mes actual por empleado
(incluida la sesión abierta), aislada por empresa/tienda, y no cuenta fichajes de meses anteriores.
"""

import datetime

import pytest

pytestmark = pytest.mark.db


def _fcols(db):
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SHOW COLUMNS FROM fichajes")
        return [r[0] for r in cur.fetchall()]


def _ins(db, nombre, ent, sal):
    from src.db.empresa import empresa_actual_id, tienda_actual_id
    cols = ["usuario_id", "nombre_empleado", "entrada", "salida", "duracion_segundos"]
    dur = None if sal is None else int((sal - ent).total_seconds())
    vals = [999, nombre, ent, sal, dur]
    fcols = _fcols(db)
    if "id_empresa" in fcols:
        cols.append("id_empresa"); vals.append(empresa_actual_id())
    if "id_tienda" in fcols and tienda_actual_id() is not None:
        cols.append("id_tienda"); vals.append(tienda_actual_id())
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute(f"INSERT INTO fichajes ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})",
                    tuple(vals))
        c.commit()


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM fichajes WHERE nombre_empleado IN ('T-EMP-A','T-EMP-B')")
            c.commit()
    _b()
    yield
    _b()


def test_horas_mes_suma_por_empleado(limpia, db):
    from src.db.usuario import horas_mes_por_empleado
    hoy = datetime.date.today()
    y, m = hoy.year, hoy.month
    _ins(db, "T-EMP-A", datetime.datetime(y, m, 2, 9), datetime.datetime(y, m, 2, 17))  # 8h
    _ins(db, "T-EMP-A", datetime.datetime(y, m, 3, 9), datetime.datetime(y, m, 3, 14))  # 5h → 13h
    _ins(db, "T-EMP-B", datetime.datetime(y, m, 2, 10), datetime.datetime(y, m, 2, 18))  # 8h
    datos = {d["nombre"]: d for d in horas_mes_por_empleado()}
    assert datos["T-EMP-A"]["horas"] == 13.0 and datos["T-EMP-A"]["fichajes"] == 2
    assert datos["T-EMP-B"]["horas"] == 8.0 and datos["T-EMP-B"]["fichajes"] == 1


def test_fichajes_empleado_por_mes_y_meses(limpia, db):
    from src.db.usuario import listar_fichajes_empleado, meses_con_fichajes_empleado
    from src.db.conexion import obtener_conexion
    hoy = datetime.date.today()
    y, m = hoy.year, hoy.month
    prev = hoy.replace(day=1) - datetime.timedelta(days=1)
    # 2 fichajes de un empleado concreto (usuario_id 424242) en el mes actual + 1 el mes anterior.
    def _ins_uid(uid, ent, sal):
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        cols = ["usuario_id", "nombre_empleado", "entrada", "salida", "duracion_segundos"]
        vals = [uid, "T-EMP-A", ent, sal, int((sal - ent).total_seconds())]
        fcols = _fcols(db)
        if "id_empresa" in fcols:
            cols.append("id_empresa"); vals.append(empresa_actual_id())
        if "id_tienda" in fcols and tienda_actual_id() is not None:
            cols.append("id_tienda"); vals.append(tienda_actual_id())
        with obtener_conexion() as c:
            cur = c.cursor()
            cur.execute(f"INSERT INTO fichajes ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})",
                        tuple(vals))
            c.commit()
    uid = 424242
    with obtener_conexion() as c:
        c.cursor().execute("DELETE FROM fichajes WHERE usuario_id=%s", (uid,)); c.commit()
    try:
        _ins_uid(uid, datetime.datetime(y, m, 1, 9), datetime.datetime(y, m, 1, 17))
        _ins_uid(uid, datetime.datetime(y, m, 2, 9), datetime.datetime(y, m, 2, 13))
        _ins_uid(uid, datetime.datetime(prev.year, prev.month, 10, 8), datetime.datetime(prev.year, prev.month, 10, 16))
        # Mes actual → 2 fichajes; el mes anterior aparece en la lista de meses.
        assert len(listar_fichajes_empleado(uid, y, m)) == 2
        assert len(listar_fichajes_empleado(uid, prev.year, prev.month)) == 1
        meses = meses_con_fichajes_empleado(uid)
        assert (y, m) in meses and (prev.year, prev.month) in meses
        assert meses[0] == (y, m)   # más reciente primero
    finally:
        with obtener_conexion() as c:
            c.cursor().execute("DELETE FROM fichajes WHERE usuario_id=%s", (uid,)); c.commit()


def test_horas_mes_excluye_meses_anteriores(limpia, db):
    from src.db.usuario import horas_mes_por_empleado
    hoy = datetime.date.today()
    # Un fichaje de hace ~3 meses no debe contar en el mes en curso.
    anterior = (hoy.replace(day=1) - datetime.timedelta(days=75))
    _ins(db, "T-EMP-A", datetime.datetime(anterior.year, anterior.month, anterior.day, 9),
         datetime.datetime(anterior.year, anterior.month, anterior.day, 20))  # 11h, mes pasado
    _ins(db, "T-EMP-A", datetime.datetime(hoy.year, hoy.month, 1, 9),
         datetime.datetime(hoy.year, hoy.month, 1, 12))  # 3h, mes en curso
    datos = {d["nombre"]: d for d in horas_mes_por_empleado()}
    assert datos["T-EMP-A"]["horas"] == 3.0        # solo el del mes en curso
