# -*- coding: utf-8 -*-
"""Utilidades de texto compartidas."""

# Siglas/acrónimos del dominio de la app que NUNCA deben perder las mayúsculas al mostrarse,
# aunque el valor subyacente (código interno, clave de dominio, tipo de integración...) esté
# en minúsculas en BD/config. Añadir aquí cualquier sigla nueva que aparezca como código interno.
SIGLAS = {
    "kpi", "kpis", "crm", "rrhh", "rfid", "mfa", "totp", "mrp", "gmao", "rma", "moq", "b2b",
    "ean", "sku", "pdf", "csv", "xml", "json", "api", "sql", "html", "css", "url", "uri", "aws",
    "cif", "nif", "iban", "tpv", "pim", "seo", "wysiwyg", "erp", "kyb", "fifo", "fefo", "esl",
    "rgpd", "wms", "sat", "pos", "ia", "ml", "llm", "otp", "iva",
}


def capitalizar_sigla(texto: str) -> str:
    """Como `str.capitalize()`, pero reconoce las SIGLAS del dominio (p. ej. "rrhh", "crm") y
    las deja en mayúsculas en vez de convertirlas en "Rrhh"/"Crm"."""
    if not texto:
        return texto
    if texto.lower() in SIGLAS:
        return texto.upper()
    return texto.capitalize()
