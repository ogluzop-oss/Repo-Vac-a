"""
Proveedores de claves criptográficas para fiscalidad (C3.5, decisión D6).

`ProveedorClaves` abstrae el origen de la clave/certificado para TLS y firma, de
modo que TLS (C3.5.2) y XAdES (C3.5.3) NO dependan de dónde vive la clave:

- `ClavesLocales`  : PKCS#12 cifrado en BD (custodia), descifrado en memoria. (C3.5.1)
- `ClavesHSM`      : HSM/PKCS#11 — interfaz DISEÑADA, no implementada. (futuro)
- `ClavesKMS`      : KMS en la nube — interfaz DISEÑADA, no implementada. (futuro)

La clave nunca toca el disco (D3). En HSM/KMS la clave privada NO es extraíble:
por eso el contrato ofrece `firmar()` (operación delegable) además del material
local, y `clave_privada()` puede ser None.
"""

from src.services.fiscal.claves.base import (ClavesHSM, ClavesKMS,
                                             ProveedorClaves)
from src.services.fiscal.claves.locales import ClavesLocales

__all__ = ["ProveedorClaves", "ClavesLocales", "ClavesHSM", "ClavesKMS"]
