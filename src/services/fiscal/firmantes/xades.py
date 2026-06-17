"""
`FirmanteXAdES` (C3.5.3) — firma XAdES de documentos XML con `signxml`.

Perfil **XAdES-EPES** cuando se aporta una política de firma; **XAdES-BES** si no.
Reutilizable para NO-VERIFACTU y Facturae (C3.4 aporta la política de Facturae).
La clave/cert vienen del `ProveedorClaves` (custodia C3.5.1), en memoria (D3).

`signxml` (lxml + cryptography, ya presentes) → empaquetado simple (decisión D1).
"""

import logging

from src.services.fiscal.base import Firmante

logger = logging.getLogger("fiscal.firmante.xades")


def politica_epes(identifier: str, description: str, digest_value_b64: str,
                  digest_method: str = "http://www.w3.org/2000/09/xmldsig#sha1"):
    """Construye una política de firma XAdES-EPES (la usará Facturae en C3.4)."""
    from signxml.xades import XAdESSignaturePolicy
    return XAdESSignaturePolicy(Identifier=identifier, Description=description,
                                DigestMethod=digest_method, DigestValue=digest_value_b64)


class FirmanteXAdES(Firmante):
    nombre = "xades"

    def __init__(self, proveedor_claves, policy=None, claimed_roles=None):
        self.claves = proveedor_claves
        self.policy = policy                      # None → XAdES-BES; objeto → EPES
        self.claimed_roles = claimed_roles

    def disponible(self) -> bool:
        return self.claves is not None and self.claves.disponible()

    def _pem(self):
        from cryptography.hazmat.primitives import serialization as s
        key = self.claves.clave_privada()
        cert = self.claves.certificado()
        key_pem = key.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption())
        cert_pem = cert.public_bytes(s.Encoding.PEM)
        return key_pem, cert_pem

    def firmar_xml(self, xml, reference_uri=None) -> bytes | None:
        """Firma un XML (bytes o Element lxml) → bytes del XML firmado, o None.
        `reference_uri` (p. ej. '#id') firma ese elemento; None firma el documento."""
        if not self.disponible():
            logger.warning("FirmanteXAdES no disponible (sin certificado).")
            return None
        try:
            from lxml import etree
            from signxml.xades import XAdESSigner
            if isinstance(xml, str):
                xml = xml.encode("utf-8")
            data = etree.fromstring(xml) if isinstance(xml, bytes) else xml
            key_pem, cert_pem = self._pem()
            signer = XAdESSigner(signature_policy=self.policy,
                                 claimed_roles=self.claimed_roles)
            firmado = signer.sign(data, key=key_pem, cert=cert_pem,
                                  reference_uri=reference_uri)
            return etree.tostring(firmado)
        except Exception as e:
            logger.error("Error firmando XAdES: %s", e)
            return None

    def firmar(self, datos: bytes) -> bytes | None:
        """Firma binaria cruda (interfaz `Firmante`). Para HSM se delega en la clave."""
        return self.claves.firmar(datos) if self.disponible() else None
