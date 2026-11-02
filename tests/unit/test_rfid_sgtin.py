"""
Codificación/decodificación EPC SGTIN-96 (`services.rfid.sgtin`) — unit, sin BD. Cubre las 7
particiones del EPC Tag Data Standard, los bordes del número de serie (38 bits) y la degradación
honesta ante entradas inválidas (nunca lanza, nunca inventa una trama)."""

import pytest

from src.services.rfid import sgtin

EAN_VALIDO = "2048237988256"  # GTIN-13 interno válido (prefijo '20' + control correcto)


def test_round_trip_basico():
    enc = sgtin.codificar_sgtin96(EAN_VALIDO, 1, prefijo_digitos=7)
    assert enc is not None
    assert len(enc["epc_hex"]) == 24
    dec = sgtin.decodificar_sgtin96(enc["epc_hex"])
    assert dec["codigo_articulo"] == EAN_VALIDO
    assert dec["numero_serie"] == 1


@pytest.mark.parametrize("prefijo_digitos", [12, 11, 10, 9, 8, 7, 6])
def test_round_trip_todas_las_particiones(prefijo_digitos):
    enc = sgtin.codificar_sgtin96(EAN_VALIDO, 42, prefijo_digitos=prefijo_digitos)
    assert enc is not None
    dec = sgtin.decodificar_sgtin96(enc["epc_hex"])
    assert dec["codigo_articulo"] == EAN_VALIDO
    assert dec["numero_serie"] == 42


def test_serial_en_los_bordes_del_rango():
    for serial in (0, 1, sgtin.SERIAL_MAXIMO):
        enc = sgtin.codificar_sgtin96(EAN_VALIDO, serial)
        assert enc is not None
        dec = sgtin.decodificar_sgtin96(enc["epc_hex"])
        assert dec["numero_serie"] == serial


def test_serial_fuera_de_rango_degrada_honesto():
    assert sgtin.codificar_sgtin96(EAN_VALIDO, -1) is None
    assert sgtin.codificar_sgtin96(EAN_VALIDO, sgtin.SERIAL_MAXIMO + 1) is None
    assert sgtin.codificar_sgtin96(EAN_VALIDO, "no-es-un-numero") is None


def test_codigo_no_gtin13_degrada_honesto():
    assert sgtin.codificar_sgtin96("123", 1) is None            # demasiado corto
    assert sgtin.codificar_sgtin96("ABCDEFGHIJKLM", 1) is None  # no numérico
    assert sgtin.codificar_sgtin96(None, 1) is None


def test_prefijo_digitos_invalido_degrada_honesto():
    assert sgtin.codificar_sgtin96(EAN_VALIDO, 1, prefijo_digitos=5) is None


def test_decodificar_entrada_malformada_degrada_honesto():
    assert sgtin.decodificar_sgtin96("no-es-hex") is None
    assert sgtin.decodificar_sgtin96("ABCD") is None             # longitud incorrecta
    assert sgtin.decodificar_sgtin96("0" * 24) is None            # cabecera distinta de SGTIN-96


def test_dos_articulos_distintos_mismo_serial_dan_epcs_distintos():
    from src.utils.ean import digito_control
    cuerpo = "209876543210"
    otro_ean = f"{cuerpo}{digito_control(cuerpo)}"
    enc1 = sgtin.codificar_sgtin96(EAN_VALIDO, 1)
    enc2 = sgtin.codificar_sgtin96(otro_ean, 1)
    assert enc1["epc_hex"] != enc2["epc_hex"]


def test_mismo_articulo_distinto_serial_da_epc_distinto():
    enc1 = sgtin.codificar_sgtin96(EAN_VALIDO, 1)
    enc2 = sgtin.codificar_sgtin96(EAN_VALIDO, 2)
    assert enc1["epc_hex"] != enc2["epc_hex"]
