"""
Taxonomía de familias de productos a granel (báscula del TPV) — fuente ÚNICA de verdad.

Clasifica todo producto de la báscula en una de las familias canónicas. Dos familias tienen
subfamilias (apartados) obligatorias:

  * PANES     → Barras de pan · Hogazas · Panecillos
  * BOLLERÍA  → Bollería dulce · Bollería salada

El resto de familias no tienen subfamilia. Reutilizado por el servicio (`bulk_products_service`),
la báscula (`_BasculaDialog`) y la gestión de precios (`_GestionGranelDialog`/`_EditarGranelDialog`).
Migrar/añadir familias aquí NO requiere tocar la GUI (la interfaz se genera a partir de esta tabla).
"""

from __future__ import annotations

# (codigo canónico, etiqueta, emoji, [subfamilias]) — el orden define el orden de las pestañas.
_FAMILIAS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    ("DULCES",      "Dulces",      "🍬", []),
    ("FRUTA",       "Fruta",       "🍎", []),
    ("VERDURA",     "Verdura",     "🥕", []),
    ("CARNICERIA",  "Carnicería",  "🥩", []),
    ("PESCADERIA",  "Pescadería",  "🐟", []),
    ("PANES",       "Panes",       "🥖", [
        ("BARRAS",     "Barras de pan"),
        ("HOGAZAS",    "Hogazas"),
        ("PANECILLOS", "Panecillos"),
    ]),
    ("BOLLERIA",    "Bollería",    "🥐", [
        ("DULCE",      "Bollería dulce"),
        ("SALADA",     "Bollería salada"),
    ]),
    ("LACTEOS",     "Lácteos / Quesos", "🧀", []),
    ("FRUTOS_SECOS", "Frutos secos", "🥜", []),
]

# Familia técnica de reserva: cualquier categoría legacy/desconocida cae aquí para NO perder productos
# ni ocultarlos. La GUI la muestra solo si contiene productos.
FAMILIA_OTROS = "OTROS"
_OTROS = ("OTROS", "Otros", "🛒", [])

# Familias que se venden por UNIDADES (no por peso): panes y bollería. El precio guardado en
# `precio_kg` se interpreta como precio por unidad y el total = unidades × precio.
_POR_UNIDAD = {"PANES", "BOLLERIA"}


def vendido_por_unidad(familia: str) -> bool:
    """True si la familia se vende por número de unidades (Panes/Bollería); False si por peso."""
    return (familia or "").upper() in _POR_UNIDAD

# Reasignación de categorías antiguas (texto libre) a las familias canónicas.
_LEGACY = {
    "FRUTA": "FRUTA",
    "VERDURA": "VERDURA",
    "DULCES": "DULCES",
    "FRUTOS SECOS": "FRUTOS_SECOS",
    "FRUTOS_SECOS": "FRUTOS_SECOS",
    "CARNE": "CARNICERIA",
    "CARNICERIA": "CARNICERIA",
    "CARNICERÍA": "CARNICERIA",
    "PESCADO": "PESCADERIA",
    "PESCADERIA": "PESCADERIA",
    "PESCADERÍA": "PESCADERIA",
    "PANES": "PANES",
    "PAN": "PANES",
    "BOLLERIA": "BOLLERIA",
    "BOLLERÍA": "BOLLERIA",
    "LACTEOS": "LACTEOS",
    "LÁCTEOS": "LACTEOS",
    "QUESOS": "LACTEOS",
    # FRESCOS era un cajón mixto (jamón + queso). Su reparto por producto se resuelve en la migración;
    # como familia por defecto, cae a lácteos (el jamón se reasigna explícitamente a carnicería).
    "FRESCOS": "LACTEOS",
}

_BY_CODE = {f[0]: f for f in _FAMILIAS}
_BY_CODE[_OTROS[0]] = _OTROS


def familias(incluir_otros: bool = False) -> list[dict]:
    """Lista de familias canónicas: [{codigo, etiqueta, emoji, subfamilias:[{codigo,etiqueta}]}]."""
    base = list(_FAMILIAS) + ([_OTROS] if incluir_otros else [])
    return [{"codigo": c, "etiqueta": et, "emoji": e,
             "por_unidad": c in _POR_UNIDAD,
             "subfamilias": [{"codigo": sc, "etiqueta": set_} for sc, set_ in subs]}
            for c, et, e, subs in base]


def codigos(incluir_otros: bool = False) -> list[str]:
    return [f["codigo"] for f in familias(incluir_otros=incluir_otros)]


def subfamilias(familia: str) -> list[dict]:
    """Subfamilias (apartados) de una familia; [] si no tiene."""
    f = _BY_CODE.get((familia or "").upper())
    if not f:
        return []
    return [{"codigo": sc, "etiqueta": set_} for sc, set_ in f[3]]


def tiene_subfamilias(familia: str) -> bool:
    return bool(subfamilias(familia))


def etiqueta(familia: str) -> str:
    f = _BY_CODE.get((familia or "").upper())
    return f[1] if f else (familia or "—")


def etiqueta_subfamilia(familia: str, sub: str) -> str:
    for s in subfamilias(familia):
        if s["codigo"] == (sub or "").upper():
            return s["etiqueta"]
    return sub or "—"


def emoji(familia: str) -> str:
    f = _BY_CODE.get((familia or "").upper())
    return f[2] if f else "🛒"


def es_valida(familia: str) -> bool:
    return (familia or "").upper() in _BY_CODE and (familia or "").upper() != FAMILIA_OTROS


def normalizar(categoria: str | None) -> str:
    """Mapea una categoría (canónica o legacy/texto libre) a un código de familia canónico.
    Lo desconocido cae en OTROS (no se pierde)."""
    if not categoria:
        return FAMILIA_OTROS
    c = categoria.strip().upper()
    if c in _BY_CODE:
        return c
    return _LEGACY.get(c, FAMILIA_OTROS)


def normalizar_subfamilia(familia: str, sub: str | None) -> str:
    """Devuelve una subfamilia válida para la familia dada (o '' si la familia no tiene subfamilias)."""
    subs = subfamilias(familia)
    if not subs:
        return ""
    s = (sub or "").strip().upper()
    validos = {x["codigo"] for x in subs}
    if s in validos:
        return s
    return subs[0]["codigo"]  # por defecto, la primera subfamilia
