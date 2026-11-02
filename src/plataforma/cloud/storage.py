"""
Cloud · Storage Abstraction (Fase VI · Bloque 11). Capa `StorageProvider` PREPARADA para almacenamiento
distribuido: Local, S3, Azure Blob, Google Cloud Storage y MinIO. NO implementa proveedores (no hay
credenciales ni SDK cloud): define el contrato común (put/get/delete/exists/url) y un proveedor Local
degradable para pruebas. Al conectar un proveedor real, el resto de la app no cambia.
"""

from __future__ import annotations

import os

PROVEEDORES = ("local", "s3", "azure_blob", "gcs", "minio")


class StorageProvider:
    """Contrato común de almacenamiento de objetos. Los proveedores cloud lo implementan sin cambiar
    a los consumidores (subir/descargar documentos, backups, grabaciones…)."""

    nombre = "abstract"

    def put(self, clave, datos: bytes) -> bool:
        raise NotImplementedError

    def get(self, clave) -> bytes | None:
        raise NotImplementedError

    def delete(self, clave) -> bool:
        raise NotImplementedError

    def exists(self, clave) -> bool:
        raise NotImplementedError

    def url(self, clave) -> str:
        raise NotImplementedError


class LocalStorage(StorageProvider):
    """Proveedor Local (degradable): almacena bajo `documentos/cloud_storage/`. Es el fallback."""

    nombre = "local"

    def __init__(self, base=None):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))))
        self.base = base or os.path.join(raiz, "documentos", "cloud_storage")
        os.makedirs(self.base, exist_ok=True)

    def _ruta(self, clave):
        return os.path.join(self.base, clave.replace("..", "_"))

    def put(self, clave, datos):
        r = self._ruta(clave); os.makedirs(os.path.dirname(r) or self.base, exist_ok=True)
        with open(r, "wb") as f:
            f.write(datos if isinstance(datos, (bytes, bytearray)) else str(datos).encode())
        return True

    def get(self, clave):
        r = self._ruta(clave)
        if not os.path.isfile(r):
            return None
        with open(r, "rb") as f:
            return f.read()

    def delete(self, clave):
        r = self._ruta(clave)
        if os.path.isfile(r):
            os.remove(r); return True
        return False

    def exists(self, clave):
        return os.path.isfile(self._ruta(clave))

    def url(self, clave):
        return f"file://{self._ruta(clave)}"


def proveedor(nombre="local", **kw) -> StorageProvider:
    """Devuelve el proveedor solicitado. Los cloud (s3/azure/gcs/minio) están PREPARADOS: hasta que
    se implementen, se degrada a Local para no romper el flujo."""
    if nombre in PROVEEDORES and nombre != "local":
        # Preparado: aquí se instanciaría el SDK real (boto3, azure-storage, google-cloud-storage…).
        return LocalStorage(**kw)
    return LocalStorage(**kw)


__all__ = ["PROVEEDORES", "StorageProvider", "LocalStorage", "proveedor"]
