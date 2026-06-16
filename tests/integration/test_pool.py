"""Integración · pool de conexiones transparente (A2.1)."""

import threading

import pytest

pytestmark = pytest.mark.db


def test_pool_disponible_y_registrado(db):
    assert db._POOL_DISPONIBLE is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    # El pool de la BD activa queda registrado (clave por configuración).
    assert db._clave_pool(db.DB_CONFIG) in db._POOLS


def test_mismo_pool_se_reutiliza(db):
    p1 = db._obtener_pool(db.DB_CONFIG)
    p2 = db._obtener_pool(db.DB_CONFIG)
    assert p1 is p2          # no se crea un pool nuevo por operación


def test_autocommit_se_mantiene(db):
    # A2.1 NO cambia la semántica: autocommit sigue activo.
    with db.obtener_conexion() as conn:
        assert db.DB_CONFIG.get("autocommit") is True
        # La conexión del pool refleja autocommit del creador.
        assert getattr(conn, "get_autocommit", lambda: True)() in (True, 1)


def test_conexiones_concurrentes(db):
    errores = []
    resultados = []

    def trabajo():
        try:
            with db.obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                resultados.append(cur.fetchone()[0])
        except Exception as e:  # pragma: no cover
            errores.append(repr(e))

    hilos = [threading.Thread(target=trabajo) for _ in range(30)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert not errores and resultados.count(1) == 30


def test_uso_secuencial_repetido(db):
    # Muchas operaciones seguidas funcionan reutilizando el pool (sin agotarse).
    for _ in range(50):
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
