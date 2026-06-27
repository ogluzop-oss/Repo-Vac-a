"""
Backends de almacenamiento de backups off-site (DR-C).

Desacoplado: LocalStorage operativo; ObjectStorage/S3/Azure/GCS son adaptadores que NO requieren
credenciales/SDK (degradan a 'no_configurado' si faltan). API: subir(ruta_local)→ref, existe(ref).
El backend se elige por env SM_DR_STORAGE (local|s3|azure|gcs|object).
"""

import logging
import os
import shutil

logger = logging.getLogger("dr.storage")


class StorageBackend:
    codigo = "base"
    def subir(self, ruta_local) -> dict:
        raise NotImplementedError
    def existe(self, ref) -> bool:
        return False


class LocalStorage(StorageBackend):
    codigo = "local"
    def _dir(self):
        base = os.path.join("documentos", "dr_offsite")
        try:
            from src.utils.recursos import ruta_datos
            base = ruta_datos("dr_offsite")
        except Exception:
            pass
        os.makedirs(base, exist_ok=True)
        return base
    def subir(self, ruta_local) -> dict:
        if not ruta_local or not os.path.exists(ruta_local):
            return {"ok": False, "estado": "origen_inexistente"}
        destino = os.path.join(self._dir(), os.path.basename(ruta_local))
        try:
            shutil.copy2(ruta_local, destino)
            return {"ok": True, "backend": self.codigo, "ref": destino}
        except Exception as e:
            logger.error("LocalStorage.subir: %s", e)
            return {"ok": False, "estado": str(e)}
    def existe(self, ref) -> bool:
        return bool(ref) and os.path.exists(ref)


class _RemotoNoConfigurado(StorageBackend):
    """Adaptador remoto declarado (S3/Azure/GCS/Object): requiere SDK+credenciales reales."""
    def subir(self, ruta_local) -> dict:
        return {"ok": False, "estado": "no_configurado", "backend": self.codigo}
    def existe(self, ref) -> bool:
        return False


class S3Storage(_RemotoNoConfigurado): codigo = "s3"
class AzureStorage(_RemotoNoConfigurado): codigo = "azure"
class GCSStorage(_RemotoNoConfigurado): codigo = "gcs"
class ObjectStorage(_RemotoNoConfigurado): codigo = "object"

_BACKENDS = {b.codigo: b for b in (LocalStorage, S3Storage, AzureStorage, GCSStorage, ObjectStorage)}


def backend(codigo=None) -> StorageBackend:
    return _BACKENDS.get((codigo or os.getenv("SM_DR_STORAGE", "local")).lower(), LocalStorage)()
