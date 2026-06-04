"""
SOMA Engine — Command parsing and routing for Smart Manager AI.
Supports navigation, real-time DB queries, contextual info, direct actions,
module-close commands and per-module help.
All comparisons are accent-insensitive and case-insensitive.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("soma.engine")


def _norm(s: str) -> str:
    """Uppercase + strip diacritics for accent-insensitive matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.upper())
        if unicodedata.category(c) != "Mn"
    )


# Fragments of SOMA's own greeting phrases. If the mic hears these back,
# it's the assistant hearing itself — must be ignored, never parsed.
_ECO_SALUDO = (
    "QUE NECESITAS", "TE ESCUCHO", "A TUS ORDENES", "AQUI ESTOY",
    "PUEDO AYUDARTE", "EN QUE TE AYUDO", "SI DIME", "DIME",
)


def _es_eco_saludo(normalizado: str) -> bool:
    n = normalizado.strip()
    if not n:
        return False
    return any(frag in n for frag in _ECO_SALUDO)


def _extraer_articulo(texto_norm: str) -> str:
    """Extracts article code or name from a normalised transcription."""
    patrones = [
        r"DEL ARTICULO\s+(.+)",
        r"DEL PRODUCTO\s+(.+)",
        r"SOBRE EL ARTICULO\s+(.+)",
        r"SOBRE\s+(.+)",
        r"HAY DE\s+(.+)",
        r"UNIDADES DE\s+(.+)",
        r"STOCK DE\s+(.+)",
        r"DE\s+(\S+)\s*$",
    ]
    for p in patrones:
        m = re.search(p, texto_norm)
        if m:
            return m.group(1).strip()
    words = texto_norm.split()
    return words[-1] if words else ""


# ---------------------------------------------------------------------------
# Per-module synonyms — used both for "abre X", "cierra X" and "comandos X".
# Each module id maps to the spoken keywords that identify it.
# ---------------------------------------------------------------------------
_MODULO_SINONIMOS: dict[str, tuple[str, ...]] = {
    "tpv":            ("TPV", "PUNTO DE VENTA", "PUNTO VENTA", "TERMINAL",
                       "CAJA REGISTRADORA", "TE PE UVE", "TE PE VE", "TEPE UVE",
                       "TEPEUVE", "T P V", "TP V"),
    "ventas":         ("VENTAS",),
    "stock":          ("STOCK", "INVENTARIO", "EXISTENCIAS"),
    "logistica":      ("RECEPCION", "RECEPCIONES", "LOGISTICA", "TRASPASO",
                       "TRASPASOS", "MERCANCIA"),
    "mermas":         ("MERMAS", "MERMA", "PERDIDAS"),
    "etiquetas":      ("ETIQUETAS", "ETIQUETA", "PRECIOS"),
    "reposicion":     ("REPOSICION", "REABASTECIMIENTO"),
    "ubicacion":      ("UBICACION", "MAPA", "PLANO"),
    "info":           ("ARTICULO", "INFORMACION DE ARTICULO", "FICHA"),
    "configuracion":  ("CONFIGURACION", "AJUSTES", "CONFIGURAR"),
    "usuarios":       ("USUARIOS", "EMPLEADOS", "PERSONAL"),
}


def _detectar_modulo(normalizado: str) -> str | None:
    """Return the module id whose synonym appears in the text, or None.

    Primero coincidencia EXACTA por subcadena; si falla, un respaldo DIFUSO
    (difflib) para que las erratas leves de Google al transcribir el nombre del
    módulo (p. ej. 'mermas' -> 'mernas', 'merca', 'mermes'...) sigan reconociéndose.
    Esto aplica a 'comandos <módulo>' y 'cierra <módulo>'."""
    # 1) Exacto.
    for modulo, sinonimos in _MODULO_SINONIMOS.items():
        for s in sinonimos:
            if _norm(s) in normalizado:
                return modulo

    # 2) Difuso: comparamos cada palabra/bigrama contra los sinónimos.
    import difflib
    palabras = normalizado.split()
    if not palabras:
        return None
    fragmentos = list(palabras) + [
        f"{palabras[i]} {palabras[i + 1]}" for i in range(len(palabras) - 1)
    ]
    mejor_mod, mejor_ratio = None, 0.0
    for modulo, sinonimos in _MODULO_SINONIMOS.items():
        for s in sinonimos:
            sn = _norm(s)
            if len(sn) < 4:   # evita sinónimos demasiado cortos (falsos positivos)
                continue
            for frag in fragmentos:
                r = difflib.SequenceMatcher(None, frag, sn).ratio()
                if r > mejor_ratio:
                    mejor_ratio, mejor_mod = r, modulo
    if mejor_ratio >= 0.80:
        logger.info(f"Módulo (difuso) '{mejor_mod}' ratio={mejor_ratio:.2f}")
        return mejor_mod
    return None


# ---------------------------------------------------------------------------
# Command table — ordered most-specific → most-generic.
# ---------------------------------------------------------------------------
_COMANDOS: list[tuple[tuple[str, ...], str]] = [

    (("CUANTO STOCK HAY", "CUANTAS UNIDADES HAY", "CUANTO HAY DE",
      "STOCK DEL ARTICULO", "STOCK DE", "UNIDADES DE", "CUANTO QUEDA DE",
      "QUEDAN UNIDADES", "HAY DE"), "query_stock"),

    (("ARTICULOS CRITICOS", "STOCK CRITICO", "QUE NECESITA REPOSICION",
      "QUE ARTICULOS FALTAN", "QUE FALTA", "BAJO MINIMO",
      "NECESITAN REPOSICION", "CRITICOS"), "query_criticos"),

    (("CUANTO HEMOS VENDIDO", "VENTAS DE HOY", "RESUMEN DE VENTAS",
      "QUE HEMOS VENDIDO", "TOTAL VENTAS", "VENTAS HOY",
      "CUANTO LLEVAMOS VENDIDO"), "query_ventas_hoy"),

    (("TRASPASOS PENDIENTES", "HAY TRASPASOS", "ENVIOS PENDIENTES",
      "DOCUMENTOS PENDIENTES", "EN TRANSITO"), "query_traspasos"),

    (("MERMAS DE ESTE MES", "CUANTAS MERMAS", "MERMAS DEL MES",
      "PERDIDAS DEL MES", "MERMAS REGISTRADAS"), "query_mermas"),

    (("QUIEN SOY", "QUIEN ESTA CONECTADO", "QUE USUARIO SOY",
      "MI USUARIO", "COMO ME LLAMO", "QUE PERFIL TENGO"), "info_usuario"),

    (("QUE HORA ES", "QUE DIA ES", "QUE FECHA ES", "DIME LA HORA",
      "DIME EL DIA", "HORA ACTUAL", "DIA DE HOY"), "info_hora"),

    (("NUEVA MERMA", "REGISTRAR MERMA", "REGISTRAR PERDIDA",
      "ANADIR MERMA", "APUNTAR MERMA"), "accion_nueva_merma"),

    (("NUEVO TRASPASO", "INICIAR TRASPASO", "INICIAR ENVIO",
      "CREAR TRASPASO", "EMPEZAR TRASPASO"), "accion_nuevo_traspaso"),

    (("BUSCA EL ARTICULO", "BUSCAR ARTICULO", "CONSULTAR ARTICULO",
      "INFORMACION DEL ARTICULO", "INFO DEL ARTICULO",
      "BUSCA EL PRODUCTO", "INFORMACION SOBRE"), "accion_buscar_articulo"),

    (("VOLVER AL MENU", "MENU PRINCIPAL", "ATRAS", "VOLVER",
      "IR AL MENU", "INICIO"), "nav_menu"),

    (("RECEPCION", "RECEPCIONES", "RECIBIR", "PALE", "MERCANCIA",
      "ABRE RECEPCION", "LOGISTICA"), "nav_recepciones"),

    (("TRASPASO", "TRASPASOS", "ENVIAR MERCANCIA", "SALIDA LOGISTICA",
      "ABRE TRASPASO", "EXPEDIR"), "nav_traspasos"),

    (("STOCK", "INVENTARIO", "EXISTENCIAS", "MOSTRAR STOCK",
      "ABRE STOCK", "VER STOCK"), "nav_stock"),

    (("VENTAS", "ABRE VENTAS", "MODULO DE VENTAS"), "nav_ventas"),

    (("TPV", "TERMINAL", "PUNTO DE VENTA", "PUNTO VENTA", "CAJA REGISTRADORA",
      "ABRE TPV", "COBRAR", "COBRO",
      "TE PE UVE", "TE PE VE", "TE PE U VE", "TEPE UVE", "TEPE VE",
      "TEPEUVE", "T P V", "TP V", "TE PE"), "nav_tpv"),

    (("MERMAS", "MERMA", "PERDIDAS", "DETERIORO", "CADUCADO",
      "ABRE MERMAS"), "nav_mermas"),

    (("ETIQUETAS", "ETIQUETA", "IMPRIMIR ETIQUETA", "IMPRIMIR PRECIO",
      "ABRE ETIQUETAS"), "nav_etiquetas"),

    (("REPOSICION", "REPONER", "INFORME DE REPOSICION",
      "ABRE REPOSICION", "REABASTECIMIENTO"), "nav_reposicion"),

    (("UBICACION", "MAPA", "PLANO", "DONDE ESTA",
      "ABRE UBICACION", "BUSCAR UBICACION"), "nav_ubicacion"),

    (("ARTICULO", "INFORMACION DE ARTICULO", "BUSCAR ARTICULO",
      "ABRE ARTICULO", "INFO ARTICULO"), "nav_info"),

    (("CONFIGURACION", "CONFIGURAR", "AJUSTES",
      "ABRE CONFIGURACION"), "nav_configuracion"),

    (("USUARIOS", "EMPLEADOS", "PERSONAL",
      "ABRE USUARIOS"), "nav_usuarios"),

    # General help. NOTE: bare "COMANDOS" (without a module) → general help.
    (("AYUDA", "HELP", "QUE PUEDES HACER", "QUE SABES",
      "QUE PUEDES", "QUE COMANDOS HAY"), "mostrar_ayuda"),

    (("CERRAR SESION", "CIERRA SESION", "SALIR", "LOGOUT",
      "DESCONECTARME", "DESCONECTAR"), "cerrar_sesion"),
]

ACCION_A_MODULO: dict[str, str] = {
    "nav_recepciones":   "logistica",
    "nav_traspasos":     "logistica",
    "nav_stock":         "stock",
    "nav_ventas":        "ventas",
    "nav_tpv":           "tpv",
    "nav_mermas":        "mermas",
    "nav_etiquetas":     "etiquetas",
    "nav_reposicion":    "reposicion",
    "nav_ubicacion":     "ubicacion",
    "nav_info":          "info",
    "nav_configuracion": "configuracion",
    "nav_usuarios":      "usuarios",
    "accion_nueva_merma":      "mermas",
    "accion_nuevo_traspaso":   "logistica",
    "accion_buscar_articulo":  "info",
}

NOMBRE_MODULO: dict[str, str] = {
    "nav_recepciones":         "recepciones",
    "nav_traspasos":           "traspasos",
    "nav_stock":               "stock",
    "nav_ventas":              "ventas",
    "nav_tpv":                 "el TPV",
    "nav_mermas":              "mermas",
    "nav_etiquetas":           "etiquetas",
    "nav_reposicion":          "reposición",
    "nav_ubicacion":           "ubicación en tienda",
    "nav_info":                "información de artículo",
    "nav_configuracion":       "configuración",
    "nav_usuarios":            "usuarios",
    "accion_nueva_merma":      "mermas",
    "accion_nuevo_traspaso":   "traspasos",
    "accion_buscar_articulo":  "información de artículo",
}

RESPUESTAS_AYUDA = (
    "Puedo abrir o cerrar cualquier módulo: recepciones, traspasos, stock, "
    "ventas, TPV, mermas, etiquetas, reposición, ubicación, artículo, "
    "configuración o usuarios. Di 'abre' o 'cierra' seguido del módulo. "
    "También respondo preguntas como cuánto stock hay de un artículo, qué "
    "artículos son críticos, cuánto hemos vendido hoy o qué hora es. "
    "Y si dices 'comandos' seguido de un módulo, te detallo qué puedes "
    "hacer en él."
)

# Per-module command catalogue, spoken when the user says "comandos <módulo>".
RESPUESTAS_COMANDOS_MODULO: dict[str, str] = {
    "tpv": (
        "En el TPV puedes decir: abre el TPV para entrar, cierra el TPV para "
        "salir. Dentro puedes pedir abrir la báscula para venta a granel, "
        "abrir devoluciones o iniciar el modo autocobro."
    ),
    "ventas": (
        "En ventas puedes preguntar cuánto hemos vendido hoy, ver el resumen "
        "de ventas, o decir abre ventas y cierra ventas."
    ),
    "stock": (
        "En stock puedes preguntar cuánto stock hay de un artículo, qué "
        "artículos son críticos o necesitan reposición, y abrir o cerrar el "
        "inventario."
    ),
    "logistica": (
        "En logística puedes abrir recepciones o traspasos, iniciar un nuevo "
        "traspaso, consultar traspasos pendientes, y cerrar el módulo."
    ),
    "mermas": (
        "En mermas puedes registrar una nueva merma, preguntar cuántas mermas "
        "hay este mes, y abrir o cerrar el módulo."
    ),
    "etiquetas": (
        "En etiquetas puedes abrir el módulo para imprimir etiquetas de precio "
        "y cerrarlo cuando termines."
    ),
    "reposicion": (
        "En reposición puedes abrir el informe de reabastecimiento y preguntar "
        "qué artículos necesitan reposición."
    ),
    "ubicacion": (
        "En ubicación puedes abrir el mapa de la tienda para localizar "
        "productos y cerrarlo después."
    ),
    "info": (
        "En artículo puedes buscar un artículo por su código o nombre para ver "
        "su ficha, y cerrar la ventana."
    ),
    "configuracion": (
        "En configuración puedes abrir los ajustes del sistema, la gestión de "
        "caja, fiscalidad, horarios o fichajes, y cerrar el módulo."
    ),
    "usuarios": (
        "En usuarios puedes abrir la gestión de empleados, consultar quién "
        "está conectado, y cerrar el módulo."
    ),
}


def _fuzzy_match(normalizado: str) -> tuple[str, str] | tuple[None, None]:
    """Fallback matcher using difflib for mild mis-transcriptions."""
    import difflib
    palabras = normalizado.split()
    if not palabras:
        return None, None
    fragmentos = list(palabras)
    fragmentos += [f"{palabras[i]} {palabras[i+1]}" for i in range(len(palabras) - 1)]
    mejor_accion = None
    mejor_kw = None
    mejor_ratio = 0.0
    for palabras_clave, accion in _COMANDOS:
        for kw in palabras_clave:
            kwn = _norm(kw)
            if len(kwn) < 4 or (" " in kwn and len(kwn) > 14):
                continue
            for frag in fragmentos:
                ratio = difflib.SequenceMatcher(None, frag, kwn).ratio()
                if ratio > mejor_ratio:
                    mejor_ratio, mejor_accion, mejor_kw = ratio, accion, kw
    if mejor_ratio >= 0.80:
        logger.info(f"Fuzzy match '{mejor_kw}' ratio={mejor_ratio:.2f}")
        return mejor_accion, mejor_kw
    return None, None


def parsear_comando(texto: str) -> tuple[str, dict]:
    """Returns (action, params) for the given voice text."""
    normalizado = _norm(texto)
    logger.debug(f"Parseando: '{normalizado}'")

    # 0a — self-heard greeting echo: ignore.
    if _es_eco_saludo(normalizado):
        logger.info("Ignorado eco del saludo de SOMA.")
        return "ignorar", {"texto": texto}

    # 0b — per-module help: "comandos <módulo>", "qué comandos tiene el TPV"...
    if "COMANDOS" in normalizado or "QUE PUEDO HACER EN" in normalizado:
        modulo = _detectar_modulo(normalizado)
        if modulo:
            logger.info(f"Ayuda de módulo: {modulo}")
            return f"help_{modulo}", {"texto": texto, "modulo": modulo}
        # "comandos" solo, sin módulo → ayuda general
        logger.info("Comandos sin módulo → ayuda general.")
        return "mostrar_ayuda", {"texto": texto}

    # 0c — close current/other module ("cierra X"), but NOT "cerrar sesión".
    _close_verbs = ("CIERRA", "CERRAR")
    if any(v in normalizado for v in _close_verbs) and "SESION" not in normalizado:
        modulo = _detectar_modulo(normalizado)
        logger.info(f"Comando de cierre de módulo detectado (modulo={modulo}).")
        return "cerrar_modulo", {"texto": texto, "modulo": modulo}

    # 1 — exact substring match (fast path).
    for palabras_clave, accion in _COMANDOS:
        for kw in palabras_clave:
            if _norm(kw) in normalizado:
                params: dict = {"texto": texto, "keyword": kw}
                if accion in ("query_stock", "accion_buscar_articulo"):
                    params["articulo"] = _extraer_articulo(normalizado)
                logger.info(f"Accion='{accion}' keyword='{kw}'")
                return accion, params

    # 2 — fuzzy fallback.
    accion, kw = _fuzzy_match(normalizado)
    if accion:
        params = {"texto": texto, "keyword": kw, "fuzzy": True}
        if accion in ("query_stock", "accion_buscar_articulo"):
            params["articulo"] = _extraer_articulo(normalizado)
        return accion, params

    logger.info(f"Sin coincidencia: '{normalizado}'")
    return "desconocido", {"texto": texto}
