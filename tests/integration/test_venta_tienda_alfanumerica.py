"""
Regresión: el contexto de tienda puede ser un código alfanumérico (p. ej. 'ALMC'),
pero la columna ventas.id_tienda es INT. registrar_venta_con_items debe coaccionarlo
y NO fallar con DataError 1366 ('Incorrect integer value').
"""
from src.db import conexion as C


def test_registrar_venta_con_tienda_alfanumerica():
    vid = C.registrar_venta_con_items(
        items=[{"codigo": "ART001", "nombre": "Regresión", "cantidad": 1,
                "precio_unitario": 1.50, "subtotal": 1.50}],
        forma_pago="efectivo", numero_caja=1, total=1.50,
        cliente={"id": 1, "nombre": "Cliente", "nif": "00000000T"},
        id_tienda="ALMC")
    assert isinstance(vid, int) and vid > 0
