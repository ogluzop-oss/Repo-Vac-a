"""
Taxonomía de TALLAS (petición explícita, 2026-11-27): tipo de artículo (Calzado/Ropa/Accesorio) →
familia demográfica (Bebés/Niños/Adolescentes/Adultos) → subfamilia → género → sistema de talla
(EU/US/UK), siempre ordenada de la talla más pequeña a la más grande.

No existía ninguna taxonomía de tallas en el repo (confirmado por auditoría previa) — este módulo
es la ÚNICA fuente de verdad, consumida tanto por el Portal B2B (`backend/portal_empresa_gestion.py`,
Alta artículo) como por el escritorio (`gui/info_articulo.py`, switch EU/US/UK + filtro). Es Python
puro, sin dependencias de Flask ni de PyQt, para poder importarse desde ambos lados sin acoplarlos.

Almacenamiento (reutilizando `producto_variantes.talla` / `equivalencias_referencia_proveedor.talla`,
ya existentes, sin motor paralelo): la talla se guarda SIEMPRE como su etiqueta EU (sistema ancla).
El "contexto" (tipo|familia|subfamilia|género, ver `contexto()`) se guarda en la columna adicional
`contexto_talla` (migración 0365) para poder convertir esa talla a US/UK sin ambigüedad — EU "38" es
a la vez una talla de calzado de mujer y de ropa de mujer, así que sin contexto no se podría
distinguir cuál de las dos tablas usar. Filas antiguas sin `contexto_talla` (antes de esta función)
siguen funcionando: `localizar_sin_contexto()` hace una búsqueda best-effort y nunca asume una talla
al azar si hay más de una coincidencia real (mismo criterio que `equivalencias_proveedor.
resolver_por_referencia`).
"""

TIPOS = ("CALZADO", "ROPA", "ACCESORIO")
FAMILIAS = ("BEBES", "NINOS", "ADOLESCENTES", "ADULTOS")
SISTEMAS = ("EU", "US", "UK")

ETIQUETAS_TIPO = {"CALZADO": "Calzado", "ROPA": "Ropa", "ACCESORIO": "Accesorio"}
ETIQUETAS_FAMILIA = {"BEBES": "Bebés", "NINOS": "Niños", "ADOLESCENTES": "Adolescentes",
                     "ADULTOS": "Adultos"}
ETIQUETAS_GENERO = {"UNISEX": "Unisex", "NINO": "Niño", "NINA": "Niña",
                    "HOMBRE": "Hombre", "MUJER": "Mujer"}
ETIQUETAS_SUBFAMILIA = {"GENERAL": "General", "PEQUENO": "Pequeño (2-7 años)",
                        "GRANDE": "Grande (8-14 años)"}

GENEROS_POR_FAMILIA = {
    "BEBES": ("UNISEX", "NINO", "NINA"),
    "NINOS": ("UNISEX", "NINO", "NINA"),
    "ADOLESCENTES": ("UNISEX", "NINO", "NINA"),
    "ADULTOS": ("UNISEX", "HOMBRE", "MUJER"),
}

SUBFAMILIAS_POR_FAMILIA = {
    "BEBES": ("GENERAL",),
    "NINOS": ("PEQUENO", "GRANDE"),
    "ADOLESCENTES": ("GENERAL",),
    "ADULTOS": ("GENERAL",),
}

_EDADES_BEBE = ["0-1 meses", "1-2 meses", "2-3 meses", "3-6 meses", "6-9 meses", "9-12 meses",
               "12-18 meses", "18-24 meses", "24-36 meses"]
_EDADES_NINO_PEQUENO = ["2-3 años", "3-4 años", "4-5 años", "5-6 años", "6-7 años"]
_EDADES_NINO_GRANDE = ["8-9 años", "9-10 años", "10-11 años", "11-12 años", "12-13 años", "13-14 años"]
_ALPHA_ADOLESCENTE = ["XS", "S", "M", "L"]
_ALPHA_ADULTO = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
_ACCESORIO_UNICO = ["Única"]
_ACCESORIO_CON_TALLAS = ["Única", "S", "M", "L", "XL"]

# ── Tablas de equivalencia CALZADO (aproximación estándar EU/US/UK, uso interno de catálogo) ─────
_CALZADO_BEBES = {"EU": ["16", "17", "18", "19"],
                  "US": ["1", "2", "2.5", "3.5"],
                  "UK": ["0", "1", "1.5", "2.5"]}
_CALZADO_NINOS_PEQUENO = {"EU": ["20", "21", "22", "23", "24", "25", "26", "27"],
                          "US": ["4", "4.5", "5.5", "6", "7", "7.5", "8.5", "9.5"],
                          "UK": ["3.5", "4", "5", "5.5", "6.5", "7", "8", "9"]}
_CALZADO_NINOS_GRANDE = {"EU": ["28", "29", "30", "31", "32", "33", "34", "35"],
                         "US": ["10", "10.5", "11.5", "12.5", "13", "13.5", "1.5", "2.5"],
                         "UK": ["10", "10.5", "11.5", "12.5", "13", "1", "2", "2.5"]}
_CALZADO_ADOLESCENTE = {"EU": ["35", "36", "37", "38", "39", "40"],
                        "US": ["3", "3.5", "4.5", "5", "5.5", "6.5"],
                        "UK": ["2.5", "3", "4", "4.5", "5", "6"]}
_CALZADO_ADULTO_HOMBRE = {"EU": ["39", "40", "41", "42", "43", "44", "45", "46", "47", "48"],
                          "US": ["6.5", "7.5", "8", "8.5", "9.5", "10.5", "11", "12", "12.5", "13.5"],
                          "UK": ["6", "6.5", "7.5", "8", "9", "9.5", "10.5", "11", "12", "13"]}
_CALZADO_ADULTO_MUJER = {"EU": ["35", "36", "37", "38", "39", "40", "41", "42"],
                         "US": ["5", "5.5", "6.5", "7", "7.5", "8.5", "9", "10"],
                         "UK": ["2.5", "3", "4", "4.5", "5.5", "6.5", "7", "8"]}


def _mismo_en_3_sistemas(lista):
    return {"EU": list(lista), "US": list(lista), "UK": list(lista)}


_ROPA_ADULTO_MUJER = {"EU": ["34", "36", "38", "40", "42", "44", "46", "48", "50", "52"],
                      "UK": ["6", "8", "10", "12", "14", "16", "18", "20", "22", "24"],
                      "US": ["2", "4", "6", "8", "10", "12", "14", "16", "18", "20"]}

# ── (tipo, familia, subfamilia, genero) -> {EU:[...], US:[...], UK:[...]} ────────────────────────
_TABLAS = {}


def _registrar(tipo, familia, subfamilia, generos, tabla):
    for genero in generos:
        _TABLAS[(tipo, familia, subfamilia, genero)] = tabla


_registrar("CALZADO", "BEBES", "GENERAL", ("UNISEX", "NINO", "NINA"), _CALZADO_BEBES)
_registrar("CALZADO", "NINOS", "PEQUENO", ("UNISEX", "NINO", "NINA"), _CALZADO_NINOS_PEQUENO)
_registrar("CALZADO", "NINOS", "GRANDE", ("UNISEX", "NINO", "NINA"), _CALZADO_NINOS_GRANDE)
_registrar("CALZADO", "ADOLESCENTES", "GENERAL", ("UNISEX", "NINO", "NINA"), _CALZADO_ADOLESCENTE)
_registrar("CALZADO", "ADULTOS", "GENERAL", ("HOMBRE", "UNISEX"), _CALZADO_ADULTO_HOMBRE)
_registrar("CALZADO", "ADULTOS", "GENERAL", ("MUJER",), _CALZADO_ADULTO_MUJER)

_registrar("ROPA", "BEBES", "GENERAL", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_EDADES_BEBE))
_registrar("ROPA", "NINOS", "PEQUENO", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_EDADES_NINO_PEQUENO))
_registrar("ROPA", "NINOS", "GRANDE", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_EDADES_NINO_GRANDE))
_registrar("ROPA", "ADOLESCENTES", "GENERAL", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_ALPHA_ADOLESCENTE))
_registrar("ROPA", "ADULTOS", "GENERAL", ("HOMBRE", "UNISEX"), _mismo_en_3_sistemas(_ALPHA_ADULTO))
_registrar("ROPA", "ADULTOS", "GENERAL", ("MUJER",), _ROPA_ADULTO_MUJER)

_registrar("ACCESORIO", "BEBES", "GENERAL", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_ACCESORIO_UNICO))
_registrar("ACCESORIO", "NINOS", "PEQUENO", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_ACCESORIO_CON_TALLAS))
_registrar("ACCESORIO", "NINOS", "GRANDE", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_ACCESORIO_CON_TALLAS))
_registrar("ACCESORIO", "ADOLESCENTES", "GENERAL", ("UNISEX", "NINO", "NINA"), _mismo_en_3_sistemas(_ACCESORIO_CON_TALLAS))
_registrar("ACCESORIO", "ADULTOS", "GENERAL", ("UNISEX", "HOMBRE", "MUJER"), _mismo_en_3_sistemas(_ACCESORIO_CON_TALLAS))


# ── API pública ────────────────────────────────────────────────────────────────────────────────
def tipos() -> list:
    return [(t, ETIQUETAS_TIPO[t]) for t in TIPOS]


def familias() -> list:
    return [(f, ETIQUETAS_FAMILIA[f]) for f in FAMILIAS]


def sistemas() -> list:
    return [(s, s) for s in SISTEMAS]


def generos(familia) -> list:
    codigos = GENEROS_POR_FAMILIA.get(str(familia).upper(), ())
    return [(g, ETIQUETAS_GENERO[g]) for g in codigos]


def subfamilias(tipo, familia) -> list:
    codigos = SUBFAMILIAS_POR_FAMILIA.get(str(familia).upper(), ("GENERAL",))
    return [(s, ETIQUETAS_SUBFAMILIA.get(s, s)) for s in codigos]


def tallas(tipo, familia, subfamilia, genero, sistema) -> list:
    """Lista ORDENADA (de la talla más pequeña a la más grande) de etiquetas de talla para esta
    combinación, en el sistema pedido. Lista vacía si la combinación no existe."""
    tabla = _TABLAS.get((str(tipo).upper(), str(familia).upper(), str(subfamilia).upper(),
                        str(genero).upper()))
    if not tabla:
        return []
    return list(tabla.get(str(sistema).upper(), []))


def contexto(tipo, familia, subfamilia, genero) -> str:
    """Cadena compacta para guardar en `contexto_talla` (migr. 0365) — identifica la tabla exacta
    usada, para poder convertir después sin ambigüedad (EU "38" es a la vez talla de calzado y de
    ropa de mujer, por ejemplo)."""
    return f"{str(tipo).upper()}|{str(familia).upper()}|{str(subfamilia).upper()}|{str(genero).upper()}"


def desde_contexto(ctx):
    """Inverso de `contexto()`. None si `ctx` no tiene el formato esperado."""
    if not ctx:
        return None
    partes = str(ctx).split("|")
    if len(partes) != 4:
        return None
    return tuple(partes)


def equivalencia_por_contexto(ctx, sistema_origen, valor) -> dict | None:
    """Dado un `contexto_talla` guardado y la talla en UN sistema, devuelve {"EU":..,"US":..,"UK":..}
    (equivalentes en los 3 sistemas, por POSICIÓN en la tabla — nunca se adivina, si `valor` no
    aparece exactamente en ese sistema devuelve None)."""
    partes = desde_contexto(ctx)
    if not partes:
        return None
    tipo, familia, subfamilia, genero = partes
    tabla = _TABLAS.get((tipo, familia, subfamilia, genero))
    if not tabla:
        return None
    lista_origen = tabla.get(str(sistema_origen).upper())
    if not lista_origen:
        return None
    try:
        idx = lista_origen.index(str(valor))
    except ValueError:
        return None
    return {s: tabla[s][idx] for s in SISTEMAS}


def localizar_sin_contexto(sistema, valor, *, genero=None) -> list:
    """Búsqueda best-effort cuando NO hay `contexto_talla` guardado (filas anteriores a esta
    función). Devuelve la lista de combinaciones (tipo,familia,subfamilia,genero) cuya tabla
    contiene `valor` en `sistema`, opcionalmente acotada por `genero` si se conoce (p. ej. desde
    `articulos.genero`) — reduce mucho la ambigüedad sin inventar nunca una talla al azar. El
    llamador debe tratar "más de 1 resultado" como ambiguo (igual criterio que
    `equivalencias_proveedor.resolver_por_referencia`)."""
    sistema = str(sistema).upper()
    valor = str(valor)
    genero = str(genero).upper() if genero else None
    encontrados = []
    for (tipo, familia, subfamilia, gen), tabla in _TABLAS.items():
        if genero and gen != genero:
            continue
        lista = tabla.get(sistema) or []
        if valor in lista:
            idx = lista.index(valor)
            encontrados.append({
                "tipo": tipo, "familia": familia, "subfamilia": subfamilia, "genero": gen,
                "contexto": contexto(tipo, familia, subfamilia, gen),
                "equivalencias": {s: tabla[s][idx] for s in SISTEMAS},
            })
    return encontrados


def estructura_js() -> dict:
    """Export completo de la taxonomía para inyectar como JSON en el Portal B2B (cascada de
    selects en el navegador, sin llamadas de red por cada cambio)."""
    out = {
        "tipos": [{"codigo": t, "etiqueta": ETIQUETAS_TIPO[t]} for t in TIPOS],
        "familias": [{"codigo": f, "etiqueta": ETIQUETAS_FAMILIA[f]} for f in FAMILIAS],
        "sistemas": list(SISTEMAS),
        "generos_por_familia": {f: [{"codigo": g, "etiqueta": ETIQUETAS_GENERO[g]}
                                    for g in GENEROS_POR_FAMILIA[f]] for f in FAMILIAS},
        "subfamilias_por_familia": {f: [{"codigo": s, "etiqueta": ETIQUETAS_SUBFAMILIA.get(s, s)}
                                        for s in SUBFAMILIAS_POR_FAMILIA[f]] for f in FAMILIAS},
        "tallas": {},
    }
    for (tipo, familia, subfamilia, genero), tabla in _TABLAS.items():
        out["tallas"].setdefault(tipo, {}).setdefault(familia, {}).setdefault(
            subfamilia, {})[genero] = {s: tabla[s] for s in SISTEMAS}
    return out
