"""
Facturae (C3.4) — factura electrónica estructurada y firmada (B2G/FACe; B2B futuro).

Régimen ORTOGONAL a Verifactu: comparte la infraestructura de C3.5 (certificado en
custodia + FirmanteXAdES + mTLS) y de C3.2 (evidencias + patrón de cola), sin tocar
el núcleo congelado. Multiempresa por id_empresa.
"""

VERSION_DEFECTO = "3.2.2"

# Namespaces oficiales por versión soportada (DF1: 3.2.2 principal, 3.2.1 compat).
NS_FACTURAE = {
    "3.2.2": "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml",
    "3.2.1": "http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_1.xml",
}
NS_DS = "http://www.w3.org/2000/09/xmldsig#"

_XSD = {"3.2.2": "Facturaev3_2_2.xsd", "3.2.1": "Facturaev3_2_1.xsd"}
