"""
Storage único (Fase 10). Fachada + factory por configuración `STORAGE_BACKEND` (local por defecto). Nunca cae
a S3 en silencio: si se pide `s3` y no está disponible, es un error explícito (no se simula). La app usa
SIEMPRE `obtener_storage()`; los módulos de negocio no acceden al filesystem directamente.
"""

import logging
import os

from src.services.storage.base import (StorageError, StorageProvider,
                                       TenantIsolationError)

logger = logging.getLogger("storage")

_INSTANCIA = None
_BACKEND_INSTANCIADO = None


def backend_configurado() -> str:
    return os.getenv("STORAGE_BACKEND", "local").lower()


def obtener_storage() -> StorageProvider:
    """Devuelve el proveedor de storage según `STORAGE_BACKEND`. Singleton por backend."""
    global _INSTANCIA, _BACKEND_INSTANCIADO
    b = backend_configurado()
    if _INSTANCIA is not None and _BACKEND_INSTANCIADO == b:
        return _INSTANCIA
    if b == "s3":
        from src.services.storage.s3 import S3StorageProvider
        _INSTANCIA = S3StorageProvider()          # falla explícito si no hay boto3/bucket (no fallback silencioso)
    elif b == "local":
        from src.services.storage.local import LocalStorageProvider
        _INSTANCIA = LocalStorageProvider()
    else:
        raise StorageError(f"STORAGE_BACKEND desconocido: {b!r}")
    _BACKEND_INSTANCIADO = b
    logger.info("storage backend = %s", _INSTANCIA.nombre)
    return _INSTANCIA


def _reset_para_tests():
    global _INSTANCIA, _BACKEND_INSTANCIADO
    _INSTANCIA = None
    _BACKEND_INSTANCIADO = None


__all__ = ["obtener_storage", "backend_configurado", "StorageProvider", "StorageError",
           "TenantIsolationError", "_reset_para_tests"]
