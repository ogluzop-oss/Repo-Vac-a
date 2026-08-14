"""Regresión de la CLASE de bug 'ALMC'.

El contexto de tienda puede ser un CÓDIGO alfanumérico ('ALMC' = Almacén Central), pero la columna
`id_tienda` es INT en 55 tablas. Todos los helpers que resuelven la tienda para esas columnas DEBEN
coaccionar el código a ENTERO (código→0) mediante el helper canónico `empresa.tienda_actual_id_int`,
evitando el error MariaDB 1366 ("Incorrect integer value: 'ALMC'"). Este test es puramente lógico
(no toca la BD): fija el contexto en memoria y comprueba la coerción.
"""


def test_helpers_tienda_coaccionan_codigo_a_int():
    from src.db.conexion import EMPRESA_DEFAULT_ID
    from src.db.empresa import set_empresa_actual, set_tienda_actual, tienda_actual_id_int
    from src.db import caja, catalogo, ventas_comercial, stock, kardex

    set_empresa_actual(EMPRESA_DEFAULT_ID)

    # Contexto = CÓDIGO 'ALMC' → todos deben devolver 0 (no la cadena 'ALMC'), sin tocar la BD.
    set_tienda_actual("ALMC")
    assert tienda_actual_id_int() == 0
    assert caja._tienda() == 0
    assert catalogo._tienda() == 0
    assert ventas_comercial._tienda() == 0
    assert stock._tienda_efectiva(None) == 0
    assert kardex._tid_col(None) == 0

    # Un id numérico se PRESERVA (no se rompe lo que ya funcionaba).
    assert caja._tienda(7) == 7
    assert catalogo._tienda(7) == 7
    assert kardex._tid_col(7) == 7

    # Sin tienda (None) se mantiene None donde la columna es nullable / se filtra por IS NULL.
    set_tienda_actual(None)
    assert caja._tienda() is None
    assert catalogo._tienda() is None
    assert ventas_comercial._tienda() is None
