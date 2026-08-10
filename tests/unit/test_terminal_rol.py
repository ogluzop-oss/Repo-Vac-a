"""
Tests · Rol del terminal (cajero vs. autocobro) — arranque por configuración, no por botón.

Verifica el resolvedor `terminal_rol`: variable de entorno (con sinónimos), consulta a
`ioc_terminales.tipo_dispositivo` por código, y el valor por defecto (TPV) degradable.
"""

import os
import uuid

import pytest

from src.services.tpv import terminal_rol as R


@pytest.fixture(autouse=True)
def _limpia_env():
    prev = {k: os.environ.get(k) for k in ("TERMINAL_ROL", "TERMINAL_TYPE", "TERMINAL_CODIGO",
                                           "TERMINAL_CAJA")}
    for k in prev:
        os.environ.pop(k, None)
    yield
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_por_defecto_es_tpv():
    assert R.rol_terminal() == R.ROL_TPV
    assert R.es_autocobro() is False
    assert R.descriptor()["fuente"] == "defecto"


def test_env_explicita_y_sinonimos():
    for val in ("AUTOCOBRO", "self_checkout", "kiosco", "TOTEM"):
        os.environ["TERMINAL_ROL"] = val
        assert R.rol_terminal() == R.ROL_AUTOCOBRO, val
    for val in ("TPV", "cajero", "tradicional"):
        os.environ["TERMINAL_ROL"] = val
        assert R.rol_terminal() == R.ROL_TPV, val


def test_env_desconocida_cae_a_defecto():
    os.environ["TERMINAL_ROL"] = "loquesea"
    assert R.rol_terminal() == R.ROL_TPV


def test_id_caja_desde_env():
    os.environ["TERMINAL_CAJA"] = "AUTO-07"
    assert R.id_caja() == "AUTO-07"


@pytest.mark.db
def test_rol_por_codigo_ioc_terminales(db):
    codigo = f"AUTO-{uuid.uuid4().hex[:8]}"
    tid = str(uuid.uuid4())
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO ioc_terminales (id, codigo_terminal, tipo_dispositivo, activo) "
                    "VALUES (%s,%s,'AUTOCOBRO',1)", (tid, codigo))
        c.commit()
    try:
        os.environ["TERMINAL_CODIGO"] = codigo
        assert R.rol_terminal() == R.ROL_AUTOCOBRO
        assert R.descriptor()["fuente"] == "ioc_terminales"
        # Un código inexistente cae al valor por defecto (degradable).
        os.environ["TERMINAL_CODIGO"] = "NO-EXISTE-XYZ"
        assert R.rol_terminal() == R.ROL_TPV
    finally:
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM ioc_terminales WHERE codigo_terminal=%s", (codigo,))
            c.commit()
