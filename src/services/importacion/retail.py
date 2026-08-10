"""
Lectores SEMÁNTICOS de retail (Fase 3): BMEcat (XML) y EDIFACT PRICAT. A diferencia de un CSV libre, estos
estándares llevan el SIGNIFICADO en la propia estructura → se normalizan directamente a los campos canónicos
(codigo/nombre/descripcion/precio/familia/stock), de modo que el mapeo queda casi automático ("hablas su
idioma"). stdlib (xml.etree + parseo de segmentos), €0. Degradable: si el fichero no es válido, devuelve [].
"""

import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger("importacion.retail")


def _local(tag) -> str:
    """Nombre de etiqueta sin espacio de nombres, en minúsculas ('{ns}ARTICLE' → 'article')."""
    return str(tag).rsplit("}", 1)[-1].lower()


def _primero(elem, nombres) -> str | None:
    """Primer descendiente cuyo localname esté en `nombres` y tenga texto."""
    for e in elem.iter():
        if _local(e.tag) in nombres:
            t = (e.text or "").strip()
            if t:
                return t
    return None


# ── BMEcat (catálogo de productos B2B, muy usado en Europa) ───────────────────
def leer_bmecat(ruta) -> list:
    """Extrae los artículos de un catálogo BMEcat. Tolera versiones/namespaces (compara por localname)."""
    try:
        root = ET.parse(ruta).getroot()
    except ET.ParseError as e:
        logger.debug("BMEcat inválido: %s", e)
        return []
    filas = []
    for art in root.iter():
        if _local(art.tag) != "article":
            continue
        codigo = _primero(art, {"supplier_aid", "supplier_pid", "international_pid", "ean", "gtin"})
        if not codigo:
            continue
        filas.append({
            "codigo": codigo,
            "nombre": _primero(art, {"description_short", "descr_short"}),
            "descripcion": _primero(art, {"description_long"}),
            "precio": _primero(art, {"price_amount"}),
            "familia": _primero(art, {"group_name", "reference_feature_group_name", "catalog_group_name"}),
        })
    return filas


# ── EDIFACT PRICAT (mensaje de catálogo/precios) ──────────────────────────────
def _componentes(dato) -> list:
    return dato.split(":")


def leer_edifact_pricat(ruta) -> list:
    """Parsea un mensaje EDIFACT PRICAT (separadores por defecto + : ' ). Agrupa por segmento LIN; toma EAN de
    LIN (C212), código de proveedor de PIA (SA), descripción de IMD, precio de PRI y cantidad de QTY. Parser
    pragmático (no cubre el carácter de escape '?'), suficiente para catálogos estándar."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(ruta, encoding=enc) as f:
                texto = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return []
    segmentos = [s.strip() for s in texto.replace("\r", "").replace("\n", "").split("'") if s.strip()]
    filas, actual = [], None
    for seg in segmentos:
        p = seg.split("+")
        tag = p[0]
        if tag == "LIN":
            if actual:
                filas.append(actual)
            ean = None
            if len(p) > 3:
                c = _componentes(p[3])
                ean = (c[0] or None) if c else None
            actual = {"codigo": ean, "nombre": None, "descripcion": None, "precio": None,
                      "stock": None, "familia": None}
        elif actual is None:
            continue
        elif tag == "PIA":
            if len(p) > 2:
                c = _componentes(p[2])
                if c and c[0] and not actual["codigo"]:
                    actual["codigo"] = c[0]
        elif tag == "IMD":
            if len(p) > 3:
                c = _componentes(p[3])
                desc = c[3] if len(c) > 3 else None
                if desc:
                    if not actual["nombre"]:
                        actual["nombre"] = desc
                    elif not actual["descripcion"]:
                        actual["descripcion"] = desc
        elif tag == "PRI":
            if len(p) > 1:
                c = _componentes(p[1])
                if len(c) > 1 and c[1]:
                    actual["precio"] = c[1]
        elif tag == "QTY":
            if len(p) > 1:
                c = _componentes(p[1])
                if len(c) > 1 and c[1]:
                    actual["stock"] = c[1]
    if actual:
        filas.append(actual)
    return [f for f in filas if f.get("codigo")]
