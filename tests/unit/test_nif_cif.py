"""
Validación de NIF (DNI) / NIE / CIF españoles (`src/utils/nif_cif.py`). Algoritmos reales (tabla
mód-23 para DNI/NIE, suma alternada + tabla JABCDEFGHI para CIF) — casos de ejemplo de uso público
habitual para pruebas de software, ninguno corresponde a una persona/empresa real.
"""

from src.utils.nif_cif import (
    normalizar_nif_cif, validar_cif, validar_documento_fiscal, validar_nie, validar_nif,
)


# ── DNI ────────────────────────────────────────────────────────────────────────────────────────
def test_dni_validos():
    assert validar_nif("12345678Z")     # 12345678 % 23 = 14 -> 'Z'
    assert validar_nif("00000000T")     # 0 % 23 = 0 -> 'T'
    assert validar_nif("11111111H")     # 11111111 % 23 = 18 -> 'H'


def test_dni_normaliza_minusculas_y_espacios():
    assert validar_nif("12345678z")
    assert validar_nif(" 12345678-Z ")
    assert normalizar_nif_cif(" 12345678-z ") == "12345678Z"


def test_dni_letra_incorrecta_invalido():
    assert not validar_nif("12345678A")
    assert not validar_nif("11111111A")


def test_dni_longitud_o_formato_invalido():
    assert not validar_nif("1234567Z")          # 7 dígitos
    assert not validar_nif("123456789Z")        # 9 dígitos
    assert not validar_nif("1234567ZZ")         # dos letras
    assert not validar_nif("")
    assert not validar_nif(None)


# ── NIE ────────────────────────────────────────────────────────────────────────────────────────
def test_nie_validos():
    assert validar_nie("X1234567L")     # X->0, 01234567 % 23 = 19 -> 'L'
    assert validar_nie("Y1234567X")     # Y->1, 11234567 % 23 = 10 -> 'X'
    assert validar_nie("Z1234567R")     # Z->2, 21234567 % 23 = 1  -> 'R'


def test_nie_normaliza_minusculas():
    assert validar_nie("x1234567l")


def test_nie_letra_control_incorrecta_invalido():
    assert not validar_nie("X1234567A")
    assert not validar_nie("Y1234567A")
    assert not validar_nie("Z1234567A")


def test_nie_prefijo_invalido():
    assert not validar_nie("A1234567L")         # solo X/Y/Z son NIE
    assert not validar_nie("X123456L")          # longitud incorrecta


# ── CIF ────────────────────────────────────────────────────────────────────────────────────────
def test_cif_grupo_solo_numerico_abeh():
    # letra 'A' (grupo ABEH: control SIEMPRE dígito) — dígitos 1234567 -> control 4.
    assert validar_cif("A12345674")
    assert not validar_cif("A12345670")         # dígito de control incorrecto
    assert not validar_cif("A1234567D")         # letra no vale para este grupo aunque coincida


def test_cif_grupo_solo_letra_kpqs():
    # letra 'K' (grupo KPQS: control SIEMPRE letra) — dígitos 7654321 -> letra 'D'.
    assert validar_cif("K7654321D")
    assert not validar_cif("K7654321X")         # letra incorrecta
    assert not validar_cif("K76543214")         # dígito no vale para este grupo (control esperado 4)


def test_cif_grupo_cualquiera_acepta_digito_o_letra():
    # letra 'C' (fuera de ABEH/KPQS): dígitos 1234567 -> dígito 4 / letra 'D', ambas válidas.
    assert validar_cif("C12345674")
    assert validar_cif("C1234567D")
    assert not validar_cif("C1234567X")         # ni el dígito ni la letra correctos


def test_cif_normaliza_minusculas():
    assert validar_cif("a12345674")


def test_cif_formato_invalido():
    assert not validar_cif("AB1234567")         # dos letras iniciales
    assert not validar_cif("A1234567")          # falta el carácter de control
    assert not validar_cif("")
    assert not validar_cif(None)


# ── Detección automática de tipo ──────────────────────────────────────────────────────────────
def test_validar_documento_fiscal_detecta_tipo():
    assert validar_documento_fiscal("12345678Z") == (True, "DNI")
    assert validar_documento_fiscal("X1234567L") == (True, "NIE")
    assert validar_documento_fiscal("A12345674") == (True, "CIF")


def test_validar_documento_fiscal_detecta_tipo_pero_invalido():
    ok, tipo = validar_documento_fiscal("12345678A")
    assert ok is False and tipo == "DNI"
    ok, tipo = validar_documento_fiscal("A12345670")
    assert ok is False and tipo == "CIF"


def test_validar_documento_fiscal_desconocido():
    assert validar_documento_fiscal("no-es-un-documento") == (False, "desconocido")
    assert validar_documento_fiscal("") == (False, "desconocido")
