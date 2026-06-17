"""
Contrato `ProveedorClaves` (C3.5) y stubs de futuros backends (HSM/KMS).

El contrato es neutro respecto al origen de la clave para que TLS (C3.5.2) y XAdES
(C3.5.3) lo usen igual con custodia local, HSM o KMS.
"""


class ProveedorClaves:
    """Origen de clave/certificado para TLS y firma. Por defecto, no disponible."""

    nombre = "base"

    def disponible(self) -> bool:
        return False

    def certificado(self):
        """Certificado X.509 (público). cryptography.x509.Certificate o None."""
        return None

    def cadena(self) -> list:
        """Certificados intermedios de la cadena (sin la raíz si no aplica)."""
        return []

    def clave_privada(self):
        """Clave privada en memoria (cryptography). None si NO es extraíble (HSM/KMS)."""
        return None

    def firmar(self, datos: bytes, hash_alg: str = "sha256") -> bytes | None:
        """Firma `datos` (operación delegable a HSM/KMS sin exponer la clave)."""
        return None

    def metadatos(self) -> dict:
        """Metadatos del certificado (nif, validez, huella, emisora…)."""
        return {}


class ClavesHSM(ProveedorClaves):
    """HSM/PKCS#11 — INTERFAZ DISEÑADA, no implementada (C3.5 deja el punto de
    extensión preparado; la implementación real es trabajo futuro)."""

    nombre = "hsm"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def disponible(self) -> bool:
        return False

    def firmar(self, datos: bytes, hash_alg: str = "sha256") -> bytes | None:
        raise NotImplementedError("ClavesHSM: pendiente (interfaz preparada en C3.5)")


class ClavesKMS(ProveedorClaves):
    """KMS en la nube — INTERFAZ DISEÑADA, no implementada (futuro)."""

    nombre = "kms"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def disponible(self) -> bool:
        return False

    def firmar(self, datos: bytes, hash_alg: str = "sha256") -> bytes | None:
        raise NotImplementedError("ClavesKMS: pendiente (interfaz preparada en C3.5)")
