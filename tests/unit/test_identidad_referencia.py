"""
Retirada de «Asignar referencia» (deprecación → Identidad Operativa/IOC). Tras la Fase 3 + migración 0175:
la pestaña se retiró, las funciones legadas son stubs y las columnas configuraciones.ref_* se eliminaron.
La identidad de la terminal se obtiene del CÓDIGO IOC de la tienda. La migración 0175 vuelca la referencia a
IOC antes de borrar (no se pierde el dato) y es reversible.
"""

import importlib

import pytest

from src.db.conexion import guardar_referencia, obtener_referencias
from src.services.identidad import identidad as ID


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _tienda(fab, db, emp, codigo):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO tiendas (codigo_tienda, nombre, id_empresa) VALUES (%s,%s,%s)",
                    (codigo, "Tienda IOC", emp))
        tid = cur.lastrowid
    fab._borrar("tiendas", "id", tid)
    return tid


def test_etiqueta_operativa_usa_codigo_ioc(fab, emp, db):
    tid = _tienda(fab, db, emp, "T-IOC01")
    assert ID.etiqueta_operativa(id_tienda=tid) == "T-IOC01"     # código IOC de la tienda


def test_etiqueta_operativa_sin_ioc_vacia():
    assert ID.etiqueta_operativa(id_tienda=999_999_99) == ""     # sin tienda con código → vacío (sin fallback)


def test_funciones_referencia_retiradas():
    # stubs de compatibilidad: no consultan las columnas eliminadas
    assert obtener_referencias() == {"ref_tienda": "", "ref_almacen": ""}
    assert guardar_referencia("tienda", "X") is False


def test_tab_asignar_referencia_retirada():
    from src.gui.gestion_usuarios import ConfiguracionWindow
    assert not hasattr(ConfiguracionWindow, "_crear_page_referencia")
    assert not hasattr(ConfiguracionWindow, "_guardar_ref")
    assert not hasattr(ConfiguracionWindow, "_migrar_ref_a_ioc")


def _cols_ref(cur):
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='configuraciones' AND COLUMN_NAME IN ('ref_tienda','ref_almacen')")
    return {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}


def test_migracion_0175_vuelca_a_ioc_y_dropa(fab, db):
    from src.services.identidad import centros as CEN
    from src.services.identidad import codigos as COD
    mod = importlib.import_module("src.database.migraciones.0175_retirar_referencia")

    emp = fab.empresa("EMP 0175")
    idc = CEN.crear_centro("Tienda Ppal", tipo="TIENDA", es_principal=True, id_empresa=emp)
    fab._borrar("ioc_centro_codigos", "id_centro", idc)
    fab._borrar("centros_trabajo", "id_centro", idc)

    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE centros_trabajo SET es_principal=1 WHERE id_centro=%s", (idc,))   # determinista
        # re-crear la columna y poner una referencia que el migrador deberá volcar
        cur.execute("ALTER TABLE configuraciones ADD COLUMN IF NOT EXISTS ref_tienda VARCHAR(100) "
                    "NOT NULL DEFAULT ''")
        cur.execute("SELECT id FROM configuraciones ORDER BY id LIMIT 1")
        row = cur.fetchone()
        tiene_fila = bool(row)
        if tiene_fila:
            rid = row[0] if not isinstance(row, dict) else list(row.values())[0]
            cur.execute("UPDATE configuraciones SET ref_tienda='MREF' WHERE id=%s", (rid,))

    with db.obtener_conexion() as c, c.cursor() as cur:
        mod.aplicar(cur)

    with db.obtener_conexion() as c, c.cursor() as cur:
        assert _cols_ref(cur) == set()              # columnas eliminadas
    if tiene_fila:
        assert COD.get_codigo(idc, "VISIBLE") == "MREF"   # la referencia se volcó a IOC antes del drop

    # reversible: revertir re-crea las columnas (vacías)
    with db.obtener_conexion() as c, c.cursor() as cur:
        mod.revertir(cur)
    with db.obtener_conexion() as c, c.cursor() as cur:
        assert _cols_ref(cur) == {"ref_tienda", "ref_almacen"}
        mod.aplicar(cur)                            # volver a dejar el esquema retirado (consistente)
