"""
Sector Comercial de empresa (Smart Suppliers B2B): antes de esta fase, `sectores_comerciales`
existía (migr. 0217) pero nunca se sembraba — ninguna empresa podía tener `sector_id` asignado,
bloqueando PERMANENTEMENTE la entrada al Portal B2B. Migración 0296 siembra las 5 ediciones del
software como sectores; `db.empresa.actualizar_empresa` ahora acepta `sector_id`; la pestaña
"Datos de empresa" de Configuración expone un desplegable para elegirlo.
"""

import pytest

pytestmark = pytest.mark.db

from src.db import empresa as emp_db
from src.services import verticales
from src.services.compras import b2b_sesion_empresa, sectores


@pytest.fixture
def emp(fab):
    return fab.empresa("SECTOR COMERCIAL TEST")


def test_migracion_siembra_los_5_sectores_de_edicion():
    todos = {s["codigo"]: s["nombre"] for s in sectores.listar()}
    for v in verticales.VERTICALES:
        assert v.lower() in todos, f"falta sembrar el sector '{v.lower()}'"


def test_actualizar_empresa_acepta_sector_id(db, emp):
    sector = sectores.listar()[0]
    ok = emp_db.actualizar_empresa(emp, sector_id=sector["id"])
    assert ok
    guardado = emp_db.obtener_empresa(emp)
    assert int(guardado["sector_id"]) == sector["id"]


def test_sin_sector_asignado_bloquea_entrada_al_portal_b2b(db, emp):
    r = b2b_sesion_empresa.crear_sesion(emp, "u1", 1, nombre_usuario="Test")
    assert r == {"ok": False, "error": "empresa_sin_sector_comercial_asignado"}


def test_con_sector_asignado_ya_no_bloquea_por_sector(db, emp, fab):
    sector = next(s for s in sectores.listar() if s["codigo"] == "retail")
    assert emp_db.actualizar_empresa(emp, sector_id=sector["id"])
    r = b2b_sesion_empresa.crear_sesion(emp, "u1", 1, nombre_usuario="Test")
    # Ya no falla por sector — si falla, es por otro motivo (p. ej. tienda inexistente en este test).
    assert r.get("error") != "empresa_sin_sector_comercial_asignado"
    if r.get("ok"):
        fab.al_limpiar(lambda: _borrar_sesion(db, r["token"]))


def _borrar_sesion(db, token):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM b2b_sesiones_empresa WHERE token_sesion=%s", (token,))
        conn.commit()
