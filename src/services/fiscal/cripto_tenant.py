"""
Cifrado en reposo DERIVADO POR TENANT (C3.5.1, decisión D4).

La clave maestra C1 (`cripto.claves_raiz`) es la RAÍZ de confianza; de ella se
DERIVA una clave efectiva por empresa con HKDF-SHA256 (salt fijo + info=id_empresa).
Así, comprometer la clave de un tenant no afecta a los demás y la rotación de la
clave maestra sigue funcionando (se derivan todas las raíces → MultiFernet).

Uso: custodia de certificados (material PKCS#12). No sustituye a `cripto` para el
resto de secretos; es específico del aislamiento fuerte SaaS de C3.5.
"""

import base64
import logging

logger = logging.getLogger("fiscal.cripto_tenant")

_SALT = b"smart-manager/fiscal/cert/v1"      # salt de dominio (no secreto)


def _derivar(root: bytes, id_empresa: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    hk = HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT,
              info=("tenant:" + str(id_empresa)).encode("utf-8"))
    return base64.urlsafe_b64encode(hk.derive(root))


def _fernet(id_empresa: str):
    """MultiFernet derivado por tenant (primera raíz cifra; todas descifran)."""
    try:
        from cryptography.fernet import Fernet, MultiFernet
        from src.utils import cripto
        raices = cripto.claves_raiz()
        if not raices:
            return None
        fernets = [Fernet(_derivar(r, id_empresa)) for r in raices]
        return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]
    except Exception as e:
        logger.error("cripto_tenant no disponible: %s", e)
        return None


def disponible() -> bool:
    from src.utils import cripto
    return cripto.cifrado_disponible()


def cifrar(datos: bytes, id_empresa: str) -> str | None:
    """Cifra bytes para un tenant → token Fernet ascii. FAIL-CLOSED (A1): si NO hay
    backend de cifrado disponible, devuelve None y NO produce ningún sustituto en
    claro. Nunca debe almacenarse material sensible sin cifrado efectivo."""
    if datos is None:
        return None
    f = _fernet(id_empresa)
    if f is None:
        logger.error("Cifrado por tenant NO disponible: se rechaza cifrar material "
                     "sensible (fail-fast). No se almacena nada en claro.")
        return None
    try:
        return f.encrypt(datos).decode("ascii")
    except Exception as e:
        logger.error("Error cifrando (tenant=%s): %s", id_empresa, e)
        return None


def descifrar(token: str, id_empresa: str) -> bytes | None:
    """Descifra un token Fernet de cifrar() para ese tenant. No se admite ningún
    formato en claro (A1): si no se puede descifrar, devuelve None."""
    if token is None or token == "":
        return None
    f = _fernet(id_empresa)
    if f is None:
        return None
    try:
        return f.decrypt(token.encode("ascii"))
    except Exception as e:
        logger.error("Error descifrando (tenant=%s): %s", id_empresa, e)
        return None


def recifrar(token: str, id_empresa: str) -> str | None:
    """Re-cifra con la clave activa del tenant (rotación de la clave maestra)."""
    datos = descifrar(token, id_empresa)
    return cifrar(datos, id_empresa) if datos is not None else token
