"""
Firma XAdES-EPES de Facturae (C3.4.3) — reutiliza `FirmanteXAdES` de C3.5.

Aplica la **política de firma oficial de Facturae** (XAdES-EPES, firma *enveloped*).
No duplica lógica de firma: solo aporta la política y el glue. Las claves/cert
vienen de la custodia (C3.5.1) vía `ProveedorClaves`.

⚠️ La política (Identifier + DigestValue) debe re-sellarse contra el PDF oficial de la
política de firma de Facturae antes de producción.
"""

import logging

logger = logging.getLogger("fiscal.facturae.firma")

# Política de firma oficial de Facturae v3.1 (aplica a 3.2.x). ⚠️[re-sellar con PDF oficial]
POLITICA_ID = ("http://www.facturae.es/politica_de_firma_formato_facturae/"
               "politica_de_firma_formato_facturae_v3_1.pdf")
POLITICA_DESC = "Política de Firma FacturaE v3.1"
POLITICA_DIGEST_SHA1_B64 = "Ohixl6upD6av8N7pEvDABhEL6hM="
POLITICA_DIGEST_METHOD = "http://www.w3.org/2000/09/xmldsig#sha1"


def politica_facturae():
    """Construye la política XAdES-EPES de Facturae (reutiliza `politica_epes`)."""
    from src.services.fiscal.firmantes import politica_epes
    return politica_epes(POLITICA_ID, POLITICA_DESC, POLITICA_DIGEST_SHA1_B64,
                         digest_method=POLITICA_DIGEST_METHOD)


def firmante_facturae(proveedor_claves):
    """`FirmanteXAdES` configurado con la política de Facturae (o None si no hay cert)."""
    if proveedor_claves is None or not proveedor_claves.disponible():
        return None
    from src.services.fiscal.firmantes import FirmanteXAdES
    return FirmanteXAdES(proveedor_claves, policy=politica_facturae(),
                         claimed_roles=["emisor"])


def firmar_facturae(xml_bytes, proveedor_claves) -> bytes | None:
    """Firma un Facturae (XAdES-EPES *enveloped*). Devuelve el XML firmado o None."""
    f = firmante_facturae(proveedor_claves)
    if f is None:
        logger.warning("Sin certificado para firmar Facturae.")
        return None
    return f.firmar_xml(xml_bytes)     # reference_uri=None → enveloped sobre todo el documento
