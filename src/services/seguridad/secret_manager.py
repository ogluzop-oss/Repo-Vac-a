"""
Vault abstraction (SEC-7) + cifrado avanzado (SEC-8).

Capa única de gestión de secretos con backends intercambiables:
  • 'fernet' (por defecto): cifra/descifra con src.utils.cripto (rotación de claves soportada).
  • 'vault'  (futuro): punto de extensión; no obliga a instalar nada.
API: cifrar/descifrar/rotar. Mantiene compatibilidad con el cifrado actual.
"""

import logging
import os

logger = logging.getLogger("seguridad.secret_manager")


def _backend():
    return os.getenv("SM_SECRET_BACKEND", "fernet").lower()


def cifrar(valor) -> str | None:
    if valor is None:
        return None
    if _backend() == "vault":
        # Punto de extensión para HashiCorp Vault / KMS (no implementado: degrada a fernet).
        logger.debug("backend vault no configurado; uso fernet")
    from src.utils import cripto
    return cripto.cifrar(valor)


def descifrar(token) -> str | None:
    if token is None:
        return None
    from src.utils import cripto
    return cripto.descifrar_seguro(token)


def rotar(token) -> str | None:
    """Re-cifra un secreto con la clave actual (rotación). Best-effort."""
    try:
        from src.utils import cripto
        if hasattr(cripto, "rotar"):
            return cripto.rotar(token)
        claro = cripto.descifrar_seguro(token)
        return cripto.cifrar(claro) if claro else token
    except Exception as e:
        logger.error("rotar: %s", e)
        return token


def obtener_secreto(clave, default=None):
    """Recupera un secreto con NOMBRE desde el backend de secretos configurado.

    backend 'vault' (futuro) → punto de extensión HashiCorp Vault / cloud KMS (no implementado).
    Fallback universal: variable de entorno homónima. Devuelve `default` si no existe.
    Permite a los módulos resolver credenciales sin fichero en disco."""
    if not clave:
        return default
    if _backend() == "vault":
        # Punto de extensión: aquí se consultaría Vault/KMS. Degrada a entorno.
        logger.debug("backend vault no configurado; resuelvo '%s' por entorno", clave)
    return os.getenv(clave, default)


def disponible_vault() -> bool:
    return False
