"""
FASE 3.3 — Framework de TIPOS DOCUMENTALES de factura.

Registro ÚNICO y extensible (no lógica rígida repartida) que define, por tipo de documento,
sus reglas: elegibilidad Verifactu, si genera fiscalidad/asiento real, serie documental
(sufijo sobre la serie base), si numera y la marca visible del PDF.

Reutiliza el campo `facturas_cliente.tipo_documento` (migr 0074). Es código (no tabla) por ser
el patrón ya usado en el proyecto (registros tipo DOMINIOS) y porque las reglas son normativas,
no configurables por empresa. Si en el futuro se requiere override por empresa, basta con una
tabla `reglas_tipo_documento` que sobrescriba este registro (aditivo).

Regla de negocio clave: una PROFORMA nunca genera IVA fiscal, ni asiento, ni Verifactu.
"""

# clave -> reglas. `serie_sufijo` "" = usa la serie base (no se renumera lo existente).
_TIPOS = {
    "factura": {
        "etiqueta": "FACTURA", "verifactu": True, "fiscal": True, "asiento": True,
        "numera": True, "serie_sufijo": "", "marca": None, "cliente_obligatorio": True,
        "estado_inicial": "emitida",
    },
    "simplificada": {
        "etiqueta": "FACTURA SIMPLIFICADA", "verifactu": True, "fiscal": True, "asiento": True,
        "numera": True, "serie_sufijo": "S", "marca": None, "cliente_obligatorio": False,
        "estado_inicial": "emitida",
    },
    "rectificativa": {  # reutiliza la infraestructura ya creada (misma serie, no se rehace)
        "etiqueta": "FACTURA RECTIFICATIVA", "verifactu": True, "fiscal": True, "asiento": True,
        "numera": True, "serie_sufijo": "", "marca": None, "cliente_obligatorio": True,
        "estado_inicial": "emitida",
    },
    "abono": {
        "etiqueta": "FACTURA DE ABONO", "verifactu": True, "fiscal": True, "asiento": True,
        "numera": True, "serie_sufijo": "", "marca": None, "cliente_obligatorio": True,
        "estado_inicial": "emitida",
    },
    "proforma": {  # documento comercial NO fiscal
        "etiqueta": "PROFORMA", "verifactu": False, "fiscal": False, "asiento": False,
        "numera": True, "serie_sufijo": "PRO", "marca": "PROFORMA", "cliente_obligatorio": False,
        "estado_inicial": "proforma",
    },
    "intracomunitaria": {
        "etiqueta": "FACTURA INTRACOMUNITARIA", "verifactu": True, "fiscal": True, "asiento": True,
        "numera": True, "serie_sufijo": "UE", "marca": None, "cliente_obligatorio": True,
        "estado_inicial": "emitida",
    },
}

_DEFECTO = "factura"


def tipos() -> list:
    """Claves de tipos soportados."""
    return list(_TIPOS.keys())


def regla(tipo) -> dict:
    """Reglas del tipo (cae a 'factura' si no se reconoce)."""
    return dict(_TIPOS.get((tipo or _DEFECTO), _TIPOS[_DEFECTO]))


def es_verifactu(tipo) -> bool:
    """¿El tipo es elegible para registro fiscal Verifactu?"""
    return bool(regla(tipo).get("verifactu"))


def genera_fiscal(tipo) -> bool:
    """¿El tipo genera fiscalidad/asiento real? (proforma → False)."""
    return bool(regla(tipo).get("fiscal"))


def estado_inicial(tipo) -> str:
    return regla(tipo).get("estado_inicial") or "emitida"


def serie_para(tipo, serie_base) -> str:
    """Serie efectiva del tipo: serie base + sufijo del tipo. Mantiene las series
    existentes (sufijo vacío) y crea series propias para proforma/simplificada/intracom."""
    base = serie_base or "A"
    suf = regla(tipo).get("serie_sufijo") or ""
    return f"{base}-{suf}" if suf else base


def marca(tipo) -> str | None:
    """Marca/agua visible del PDF (p. ej. 'PROFORMA'). None si no procede."""
    return regla(tipo).get("marca")
