"""
Validación y normalización de NIF (DNI) / NIE / CIF españoles.

Sin dependencias externas: los tres algoritmos de dígito/letra de control son los REALES publicados
por la Agencia Tributaria, igual que `utils/iban.py` implementa el mód-97 real del IBAN en vez de
aproximarlo. Se usa en la rama de importación de datos (`services/importacion/validadores.py`) para
validar CLIENTES/PROVEEDORES, y puede reutilizarse en cualquier otro punto que necesite comprobar un
documento fiscal español sin adivinar.
"""

import re

# DNI/NIE: letra de control = tabla fija indexada por (número % 23).
_TABLA_CONTROL = "TRWAGMYFPDXBNJZSQVHLCKE"

# NIE: la letra inicial se sustituye por un dígito antes de aplicar el mismo mód-23 que el DNI.
_NIE_PREFIJOS = {"X": "0", "Y": "1", "Z": "2"}

# CIF: dígito de control -> letra de control (índice = dígito 0-9).
_LETRAS_CONTROL_CIF = "JABCDEFGHI"

# CIF: según la letra inicial, el carácter de control es SIEMPRE numérico, SIEMPRE letra, o
# cualquiera de los dos es válido (entidades más antiguas, antes de unificar el criterio).
_CIF_SOLO_NUMERICO = set("ABEH")
_CIF_SOLO_LETRA = set("KPQS")

_RE_DNI = re.compile(r"^\d{8}[A-Z]$")
_RE_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_RE_CIF = re.compile(r"^[A-Z]\d{7}[0-9A-Z]$")


def normalizar_nif_cif(valor: str | None) -> str:
    """Quita espacios/guiones y pasa a mayúsculas (mismo criterio que `iban.normalizar_iban`)."""
    return re.sub(r"[\s\-]", "", (valor or "")).upper()


def validar_nif(valor: str | None) -> bool:
    """True si es un DNI español válido: 8 dígitos + letra de control (número % 23 -> tabla fija)."""
    v = normalizar_nif_cif(valor)
    if not _RE_DNI.match(v):
        return False
    numero = int(v[:8])
    return v[8] == _TABLA_CONTROL[numero % 23]


def validar_nie(valor: str | None) -> bool:
    """True si es un NIE español válido: X/Y/Z + 7 dígitos + letra de control. La letra inicial se
    sustituye por 0/1/2 respectivamente y se aplica el mismo mód-23 que el DNI sobre el número de
    8 cifras resultante."""
    v = normalizar_nif_cif(valor)
    if not _RE_NIE.match(v):
        return False
    numero = int(_NIE_PREFIJOS[v[0]] + v[1:8])
    return v[8] == _TABLA_CONTROL[numero % 23]


def _digito_control_cif(digitos: str) -> int:
    """Suma de control del CIF: dobla las cifras en posiciones impares (1ª,3ª,5ª,7ª) sumando los
    dígitos del resultado si pasa de 9 (equivale a restar 9), y suma directamente las de posiciones
    pares (2ª,4ª,6ª). El dígito de control es `(10 - total%10) % 10`."""
    suma_pares = 0
    suma_impares = 0
    for i, c in enumerate(digitos):
        n = int(c)
        if i % 2 == 0:                     # posición impar (1ª,3ª,5ª,7ª): índice 0,2,4,6
            n *= 2
            if n > 9:
                n -= 9
            suma_impares += n
        else:                              # posición par (2ª,4ª,6ª): índice 1,3,5
            suma_pares += n
    total = suma_pares + suma_impares
    return (10 - (total % 10)) % 10


def validar_cif(valor: str | None) -> bool:
    """True si es un CIF español válido: letra + 7 dígitos + carácter de control.

    El carácter de control puede ser numérico o alfabético según la letra inicial:
    - ABEH  -> el control debe ser el DÍGITO calculado.
    - KPQS  -> el control debe ser la LETRA correspondiente (tabla `JABCDEFGHI` indexada por el dígito).
    - resto -> se acepta cualquiera de las dos formas (criterio histórico, ambas circulan como válidas).
    """
    v = normalizar_nif_cif(valor)
    if not _RE_CIF.match(v):
        return False
    letra_inicial, digitos, control = v[0], v[1:8], v[8]
    digito = _digito_control_cif(digitos)
    letra = _LETRAS_CONTROL_CIF[digito]
    if letra_inicial in _CIF_SOLO_NUMERICO:
        return control == str(digito)
    if letra_inicial in _CIF_SOLO_LETRA:
        return control == letra
    return control == str(digito) or control == letra


def validar_documento_fiscal(valor: str | None) -> tuple[bool, str]:
    """Detecta el TIPO (DNI/NIE/CIF) por forma y lo valida. Devuelve `(ok, tipo)`, con
    `tipo` en {"DNI", "NIE", "CIF", "desconocido"} — útil cuando el dato de origen no dice de qué
    tipo de documento se trata (caso típico de una importación de terceros)."""
    v = normalizar_nif_cif(valor)
    if _RE_DNI.match(v):
        return validar_nif(v), "DNI"
    if _RE_NIE.match(v):
        return validar_nie(v), "NIE"
    if _RE_CIF.match(v):
        return validar_cif(v), "CIF"
    return False, "desconocido"
