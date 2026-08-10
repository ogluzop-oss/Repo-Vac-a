"""
Fase 6: `articulos` con PK compuesta (id_empresa, codigo). Dos empresas pueden tener el MISMO código de producto
(antes imposible: `codigo` era PK global). Verifica el esquema y que el importador aísla por empresa.
"""

import pytest

from src.services import importacion as I


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(fab):
    for cod in ("PK6-DUP", "PK6-IMP"):
        fab._borrar("articulos", "codigo", cod)


def test_pk_compuesta_en_esquema(db):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE "
                    "TABLE_SCHEMA=DATABASE() AND TABLE_NAME='articulos' AND CONSTRAINT_NAME='PRIMARY' "
                    "ORDER BY ORDINAL_POSITION")
        assert [r[0] for r in cur.fetchall()] == ["id_empresa", "codigo"]


def test_mismo_codigo_en_dos_empresas(db, emp):
    e2 = "pk6-emp2-aaaa-bbbb-cccc"
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,nombre,id_empresa) VALUES ('PK6-DUP','A',%s)", (emp,))
        cur.execute("INSERT INTO articulos (codigo,nombre,id_empresa) VALUES ('PK6-DUP','B',%s)", (e2,))
        c.commit()
        cur.execute("SELECT id_empresa,nombre FROM articulos WHERE codigo='PK6-DUP'")
        d = {r[0]: r[1] for r in cur.fetchall()}
    assert len(d) == 2 and d[emp] == "A" and d[e2] == "B"      # antes fallaría por PK duplicada


def test_importador_aisla_codigo_por_empresa(db, emp):
    e2 = "pk6-emp3-aaaa-bbbb-dddd"
    r1 = I.ejecutar_filas([{"codigo": "PK6-IMP", "nombre": "DeE1", "precio": 1}], id_empresa=emp, origen="t")
    r2 = I.ejecutar_filas([{"codigo": "PK6-IMP", "nombre": "DeE2", "precio": 2}], id_empresa=e2, origen="t")
    assert r1["ok"] and r2["ok"] and r1["cargados"] == 1 and r2["cargados"] == 1
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_empresa,nombre FROM articulos WHERE codigo='PK6-IMP'")
        d = {r[0]: r[1] for r in cur.fetchall()}
    assert d[emp] == "DeE1" and d[e2] == "DeE2"                # el upsert no pisa la de la otra empresa
