"""
Backend LOCAL de storage (Fase 10). Almacena bajo un directorio raíz (por defecto `documentos/_storage/`),
respetando la clave canónica `tenant/{id_empresa}/{tipo}/{nombre}`. Es el backend por defecto en DEV y el
que permite probar TODO el flujo (incluido el aislamiento multi-tenant) sin AWS. La validación de tenant vive
en la clase base; aquí sólo se materializa en filesystem de forma segura.
"""

import os

from src.services.storage.base import StorageError, StorageProvider


def _raiz() -> str:
    r = os.getenv("STORAGE_LOCAL_ROOT")
    if r:
        return r
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..", "documentos", "_storage")
    return os.path.abspath(base)


class LocalStorageProvider(StorageProvider):
    nombre = "local"

    def __init__(self, raiz=None):
        self._raiz = os.path.abspath(raiz or _raiz())

    def _ruta(self, clave) -> str:
        # `clave` ya validada por la base (sin '..', sin '/' inicial). Se ancla bajo la raíz y se
        # re-verifica que el resultado no escapa del árbol (defensa en profundidad).
        p = os.path.abspath(os.path.join(self._raiz, clave))
        if not (p == self._raiz or p.startswith(self._raiz + os.sep)):
            raise StorageError(f"ruta fuera de la raíz de storage: {clave!r}")
        return p

    def _put_raw(self, clave, datos, *, content_type=None):
        p = self._ruta(clave)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(datos if isinstance(datos, (bytes, bytearray)) else str(datos).encode("utf-8"))

    def _get_raw(self, clave):
        with open(self._ruta(clave), "rb") as f:
            return f.read()

    def _exists_raw(self, clave):
        return os.path.isfile(self._ruta(clave))

    def _delete_raw(self, clave):
        p = self._ruta(clave)
        if os.path.isfile(p):
            os.remove(p)
            return True
        return False

    def _meta_raw(self, clave):
        p = self._ruta(clave)
        st = os.stat(p)
        return {"clave": clave, "tamano": st.st_size, "modificado": st.st_mtime, "backend": "local"}

    def _list_raw(self, prefijo):
        base = self._ruta(prefijo.rstrip("/"))
        out = []
        if os.path.isdir(base):
            for raiz, _dirs, ficheros in os.walk(base):
                for fn in ficheros:
                    full = os.path.join(raiz, fn)
                    rel = os.path.relpath(full, self._raiz).replace(os.sep, "/")
                    out.append(rel)
        return sorted(out)

    def _signed_url_raw(self, clave, *, segundos):
        # No hay CDN local: se devuelve una referencia local honesta (NO es una URL S3 firmada).
        return f"local://{clave}"
