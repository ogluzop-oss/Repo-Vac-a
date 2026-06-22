"""
Validación y normalización de IBAN / BIC (ISO 13616 / ISO 9362).

Sin dependencias externas: el dígito de control IBAN se valida con el algoritmo
mód-97 (ISO 7064). Se usa en la rama de Tesorería/SEPA para garantizar que las
cuentas bancarias y las remesas llevan identificadores bancarios correctos.
"""

import re

# Longitudes oficiales de IBAN por país (las más habituales en SEPA + comunes).
LONGITUDES = {
    "ES": 24, "FR": 27, "DE": 22, "IT": 27, "PT": 25, "NL": 18, "BE": 16,
    "GB": 22, "IE": 22, "LU": 20, "AT": 20, "FI": 18, "GR": 27, "PL": 28,
    "CH": 21, "SE": 24, "DK": 18, "NO": 15, "CZ": 24, "SK": 24, "RO": 24,
    "BG": 22, "HR": 21, "HU": 28, "LT": 20, "LV": 21, "EE": 20, "SI": 19,
    "CY": 28, "MT": 31, "IS": 26, "LI": 21, "MC": 27, "SM": 27, "AD": 24,
}

_RE_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
_RE_BIC = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def normalizar_iban(iban: str | None) -> str:
    """Quita espacios/guiones y pasa a mayúsculas."""
    return re.sub(r"[\s\-]", "", (iban or "")).upper()


def validar_iban(iban: str | None) -> bool:
    """True si el IBAN es estructuralmente válido y su dígito de control (mód-97) cuadra."""
    s = normalizar_iban(iban)
    if not _RE_IBAN.match(s):
        return False
    pais = s[:2]
    if pais in LONGITUDES and len(s) != LONGITUDES[pais]:
        return False
    # Reordena (los 4 primeros al final) y convierte letras→números (A=10..Z=35).
    reordenado = s[4:] + s[:4]
    numerico = "".join(str(int(c, 36)) for c in reordenado)
    return int(numerico) % 97 == 1


def validar_bic(bic: str | None) -> bool:
    """True si el BIC/SWIFT es válido (8 u 11 caracteres). Vacío => no validado aquí."""
    return bool(_RE_BIC.match((bic or "").strip().upper()))


def mascara_iban(iban: str | None) -> str:
    """Representación segura para UI: país + '****' + 4 últimos dígitos (p.ej. ES**…**1234)."""
    s = normalizar_iban(iban)
    if len(s) < 8:
        return "****"
    return f"{s[:2]}**{'*' * max(0, len(s) - 8)}{s[-4:]}"
