"""
Fase 4: volcados SQL (.sql → staging) y conector DIRECTO (BD vía SELECT, API REST inyectable, ODBC degradable).
Todos alimentan el mismo pipeline (`ejecutar_filas`). La BD directa se prueba contra la propia BD de test.
"""

import pytest

from src.services import importacion as I
from src.services.importacion import conector as C
from src.services.importacion import dump_sql

_DUMP = """
CREATE TABLE `productos` (
  `sku` varchar(50) NOT NULL,
  `descripcion` varchar(255),
  `pvp` decimal(10,2),
  `familia` varchar(100),
  `existencias` int,
  PRIMARY KEY (`sku`)
);
INSERT INTO `productos` (`sku`,`descripcion`,`pvp`,`familia`,`existencias`) VALUES
 ('SQL-1','Cola, 1L','1.50','Bebidas',10),('SQL-2','Agua','0.90',NULL,5);
CREATE TABLE `otros` (`id` int, `x` varchar(10));
INSERT INTO otros VALUES (1,'a'),(2,'b');
"""


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(fab):
    for cod in ("SQL-1", "SQL-2", "CN-1", "CN-2", "API-1"):
        fab._borrar("articulos", "codigo", cod)
        fab._borrar("stock_tienda", "codigo_articulo", cod)
        fab._borrar("movimientos_stock", "codigo_articulo", cod)
    fab.al_limpiar(lambda: fab._borrar("familias_producto", "nombre", "Bebidas"))


def _art(db, codigo):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT nombre, precio, Stock_total FROM articulos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        return None if not r else dict(zip(["nombre", "precio", "stock"], r))


def test_dump_sql_parsea_y_elige_tabla_producto(tmp_path):
    ruta = tmp_path / "backup.sql"
    ruta.write_text(_DUMP, encoding="utf-8")
    assert set(dump_sql.tablas_dump(str(ruta))) == {"productos", "otros"}
    filas = dump_sql.leer_sql_dump(str(ruta))                 # elige 'productos' (más columnas de producto)
    assert [f["sku"] for f in filas] == ["SQL-1", "SQL-2"]
    assert filas[0]["descripcion"] == "Cola, 1L"             # coma dentro de comillas respetada
    assert filas[1]["familia"] is None                        # NULL → None


def test_dump_sql_se_carga(emp, db, tmp_path):
    ruta = tmp_path / "backup.sql"
    ruta.write_text(_DUMP, encoding="utf-8")
    res = I.ejecutar(str(ruta), id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2
    assert _art(db, "SQL-1")["nombre"] == "Cola, 1L" and _art(db, "SQL-1")["stock"] == 10


def test_conector_bd_directo(emp, db, fab):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _imp_origen")
        cur.execute("CREATE TABLE _imp_origen (codigo VARCHAR(50), nombre VARCHAR(100), "
                    "precio DECIMAL(10,2), stock INT)")
        cur.executemany("INSERT INTO _imp_origen VALUES (%s,%s,%s,%s)",
                        [("CN-1", "Directo", 2.0, 7), ("CN-2", "Directo2", 3.0, 4)])
        conn.commit()
    try:
        with db.obtener_conexion() as conn:
            filas = C.leer_consulta("SELECT codigo,nombre,precio,stock FROM _imp_origen ORDER BY codigo",
                                    conexion=conn)
        assert len(filas) == 2 and filas[0]["codigo"] == "CN-1"
        res = I.ejecutar_filas(filas, id_empresa=emp, origen="bd-directa")
        assert res["ok"] and res["cargados"] == 2
        assert _art(db, "CN-1")["stock"] == 7
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS _imp_origen")
            conn.commit()


def test_conector_api_inyectado(emp, db):
    datos = {"data": [{"codigo": "API-1", "nombre": "ApiProd", "precio": 9.99, "stock": 3}]}
    filas = C.leer_api("http://origen/productos", fetch=lambda u: datos)
    assert filas[0]["codigo"] == "API-1"
    res = I.ejecutar_filas(filas, id_empresa=emp, origen="api")
    assert res["ok"] and _art(db, "API-1")["stock"] == 3


def test_odbc_degradable_sin_dsn_valido():
    # pyodbc está presente; con un DSN inexistente falla de forma honesta (no cuelga ni finge).
    with pytest.raises(Exception):
        C.leer_odbc("Driver={NoExisteDriver};Server=nadie;Database=nada;", "SELECT 1")
