"""
Cifrado simétrico para secretos en reposo (tokens OAuth del correo corporativo).

NUNCA se almacenan contraseñas. Solo tokens OAuth 2.0, y SIEMPRE cifrados con
Fernet (AES-128 CBC + HMAC). La clave se guarda fuera del control de versiones
(documentos/.correo_key) o en la variable de entorno SMART_MANAGER_SECRET_KEY.

Si `cryptography` no estuviera disponible, degrada con un marcador claro y NO
cifra (se registra un aviso); así el resto del sistema sigue funcionando.
"""

import base64
import logging
import os

logger = logging.getLogger("cripto")

_PLANO_PREFIX = "plain:"  # marcador para valores no cifrados (degradación)
_fernet = None
_intentado = False


def _ruta_clave() -> str:
    try:
        from src.utils import recursos
        base = recursos.ruta_documentos() if hasattr(recursos, "ruta_documentos") else None
    except Exception:
        base = None
    if not base:
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "documentos",
        )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, ".correo_key")


def _cargar_o_crear_clave() -> bytes | None:
    # 1) Variable de entorno (recomendado para despliegues controlados).
    env = os.getenv("SMART_MANAGER_SECRET_KEY")
    if env:
        try:
            return env.encode() if len(env) >= 44 else base64.urlsafe_b64encode(env.ljust(32)[:32].encode())
        except Exception:
            pass
    # 2) Archivo local (gitignored).
    ruta = _ruta_clave()
    try:
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                return f.read().strip()
        from cryptography.fernet import Fernet
        clave = Fernet.generate_key()
        with open(ruta, "wb") as f:
            f.write(clave)
        logger.info("Clave de cifrado de correo generada en %s", ruta)
        return clave
    except Exception as e:
        logger.error("No se pudo cargar/crear la clave de cifrado: %s", e)
        return None


def _get_fernet():
    global _fernet, _intentado
    if _fernet is not None or _intentado:
        return _fernet
    _intentado = True
    try:
        from cryptography.fernet import Fernet
        clave = _cargar_o_crear_clave()
        if clave:
            _fernet = Fernet(clave)
    except Exception as e:
        logger.warning("Cifrado no disponible (cryptography): %s. Los tokens NO se cifrarán.", e)
        _fernet = None
    return _fernet


def cifrar(texto: str | None) -> str | None:
    """Cifra un secreto. Devuelve un token cifrado, o uno marcado 'plain:' si no
    hay backend de cifrado (degradación elegante con aviso ya registrado)."""
    if texto is None or texto == "":
        return texto
    f = _get_fernet()
    if f is None:
        return _PLANO_PREFIX + texto
    try:
        return f.encrypt(texto.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.error("Error cifrando: %s", e)
        return _PLANO_PREFIX + texto


def descifrar(token: str | None) -> str | None:
    """Descifra un token producido por cifrar()."""
    if token is None or token == "":
        return token
    if token.startswith(_PLANO_PREFIX):
        return token[len(_PLANO_PREFIX):]
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.error("Error descifrando: %s", e)
        return None


def parece_cifrado(token: str | None) -> bool:
    """True si el valor parece un token producido por `cifrar` (Fernet o 'plain:')."""
    return isinstance(token, str) and (token.startswith("gAAAA") or token.startswith(_PLANO_PREFIX))


def descifrar_seguro(token: str | None) -> str | None:
    """Descifra de forma retrocompatible: si el valor NO parece cifrado, se asume
    que es un secreto legado en claro y se devuelve tal cual (permite migrar sin
    romper lecturas)."""
    if token is None or token == "":
        return token
    if not parece_cifrado(token):
        return token            # secreto legado en claro
    return descifrar(token)


def cifrado_disponible() -> bool:
    """True si hay backend de cifrado real (cryptography + clave)."""
    return _get_fernet() is not None
