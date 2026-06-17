"""
`ClavesLocales` (C3.5.1) — claves desde PKCS#12 custodiado (cifrado en BD).

Descifra el material en MEMORIA (D3: nunca a disco) y expone clave/cert para TLS
(C3.5.2) y firma XAdES (C3.5.3). La carga del PKCS#12 se hace bajo demanda y se
mantiene solo en memoria del proceso.
"""

import logging

from src.services.fiscal.claves.base import ProveedorClaves

logger = logging.getLogger("fiscal.claves.locales")


class ClavesLocales(ProveedorClaves):
    nombre = "local"

    def __init__(self, p12_bytes: bytes = None, password: str = None, metadatos: dict = None):
        self._p12 = p12_bytes
        self._password = password
        self._meta = metadatos or {}
        self._cargado = False
        self._key = None
        self._cert = None
        self._cadena = []

    def _cargar(self):
        if self._cargado:
            return
        self._cargado = True
        if not self._p12:
            return
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            pw = self._password.encode("utf-8") if self._password else None
            key, cert, extra = pkcs12.load_key_and_certificates(self._p12, pw)
            self._key, self._cert, self._cadena = key, cert, list(extra or [])
        except Exception as e:
            logger.error("No se pudo cargar el PKCS#12: %s", e)

    def disponible(self) -> bool:
        self._cargar()
        return self._key is not None and self._cert is not None

    def certificado(self):
        self._cargar()
        return self._cert

    def cadena(self) -> list:
        self._cargar()
        return self._cadena

    def clave_privada(self):
        self._cargar()
        return self._key

    def firmar(self, datos: bytes, hash_alg: str = "sha256") -> bytes | None:
        self._cargar()
        if self._key is None:
            return None
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
            h = {"sha256": hashes.SHA256(), "sha512": hashes.SHA512()}.get(hash_alg, hashes.SHA256())
            if isinstance(self._key, rsa.RSAPrivateKey):
                return self._key.sign(datos, padding.PKCS1v15(), h)
            if isinstance(self._key, ec.EllipticCurvePrivateKey):
                return self._key.sign(datos, ec.ECDSA(h))
            return None
        except Exception as e:
            logger.error("Error firmando con clave local: %s", e)
            return None

    def metadatos(self) -> dict:
        return dict(self._meta)
