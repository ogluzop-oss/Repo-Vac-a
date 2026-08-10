"""
Abstracción ÚNICA de almacenamiento de objetos (Fase 10). Un solo `StorageProvider` para toda la app; los
módulos de negocio NUNCA tocan el filesystem directamente. Backends intercambiables por configuración
(`STORAGE_BACKEND=local|s3`). El AISLAMIENTO MULTI-TENANT se aplica AQUÍ, en la clase base, de modo que TODO
backend lo hereda: cada clave vive bajo `tenant/{id_empresa}/…` y toda operación valida el tenant antes de
tocar el objeto. Una URL firmada JAMÁS se emite sin validar `id_empresa` + autorización del usuario.
"""

import logging
import re

logger = logging.getLogger("storage")

_PREFIJO = "tenant"
_NOMBRE_OK = re.compile(r"^[A-Za-z0-9._\-]+$")     # sin '/', sin '..', sin espacios raros


class StorageError(Exception):
    pass


class TenantIsolationError(StorageError):
    """Se intentó acceder a un objeto fuera del tenant autorizado (posible fuga cross-tenant)."""


class StorageProvider:
    """Base con el guard de tenant. Los backends implementan sólo los `_*_raw` sobre la CLAVE ya validada."""

    nombre = "base"

    # ── API pública (validada) ────────────────────────────────────────────────
    def clave(self, id_empresa, tipo, nombre) -> str:
        """Construye la clave canónica `tenant/{id_empresa}/{tipo}/{nombre}` con validación estricta."""
        emp = self._emp(id_empresa)
        tipo = self._segmento(tipo, "tipo")
        nombre = self._segmento(nombre, "nombre")
        return f"{_PREFIJO}/{emp}/{tipo}/{nombre}"

    def guardar(self, id_empresa, tipo, nombre, datos: bytes, *, content_type=None) -> str:
        clave = self.clave(id_empresa, tipo, nombre)
        self._put_raw(clave, datos, content_type=content_type)
        _metrica("guardar")
        return clave

    def leer(self, id_empresa, clave) -> bytes:
        self._validar(id_empresa, clave)
        return self._get_raw(clave)

    def existe(self, id_empresa, clave) -> bool:
        self._validar(id_empresa, clave)
        return self._exists_raw(clave)

    def borrar(self, id_empresa, clave) -> bool:
        self._validar(id_empresa, clave)
        r = self._delete_raw(clave)
        _metrica("borrar")
        return r

    def metadatos(self, id_empresa, clave) -> dict:
        self._validar(id_empresa, clave)
        return self._meta_raw(clave)

    def listar(self, id_empresa, tipo=None) -> list:
        emp = self._emp(id_empresa)
        pref = f"{_PREFIJO}/{emp}/" + (f"{self._segmento(tipo, 'tipo')}/" if tipo else "")
        return self._list_raw(pref)

    def url_firmada(self, id_empresa, clave, *, segundos=300, usuario=None, autorizado=True) -> str:
        """URL/temporal de acceso. REGLA CRÍTICA: sólo se emite tras validar tenant + autorización. El
        llamador (capa de negocio) debe pasar `autorizado=` tras comprobar RBAC/permisos del `usuario`."""
        self._validar(id_empresa, clave)
        if not autorizado:
            raise TenantIsolationError(f"usuario {usuario} no autorizado para {clave}")
        _metrica("url_firmada")
        return self._signed_url_raw(clave, segundos=segundos)

    # ── Guard de tenant (heredado por todos los backends) ──────────────────────
    def _validar(self, id_empresa, clave) -> None:
        emp = self._emp(id_empresa)
        esperado = f"{_PREFIJO}/{emp}/"
        c = str(clave or "")
        if ".." in c or c.startswith("/") or "\\" in c:
            raise TenantIsolationError(f"clave insegura: {clave!r}")
        if not c.startswith(esperado):
            raise TenantIsolationError(f"clave {clave!r} fuera del tenant {emp}")

    @staticmethod
    def _emp(id_empresa) -> str:
        if id_empresa is None or str(id_empresa).strip() == "":
            raise TenantIsolationError("id_empresa obligatorio para toda operación de storage")
        s = str(id_empresa)
        if "/" in s or ".." in s:
            raise TenantIsolationError(f"id_empresa inseguro: {s!r}")
        return s

    @staticmethod
    def _segmento(v, campo) -> str:
        s = str(v or "").strip()
        if not s or not _NOMBRE_OK.match(s):
            raise StorageError(f"{campo} inválido: {v!r} (usa [A-Za-z0-9._-])")
        return s

    # ── Contrato de backend (sobre CLAVE ya validada) ─────────────────────────
    def _put_raw(self, clave, datos, *, content_type=None): raise NotImplementedError
    def _get_raw(self, clave): raise NotImplementedError
    def _exists_raw(self, clave): raise NotImplementedError
    def _delete_raw(self, clave): raise NotImplementedError
    def _meta_raw(self, clave): raise NotImplementedError
    def _list_raw(self, prefijo): raise NotImplementedError
    def _signed_url_raw(self, clave, *, segundos): raise NotImplementedError


# ── métricas (reutiliza observabilidad; degradable) ───────────────────────────
def _metrica(op):
    try:
        from src.services.observabilidad import metricas as M
        if hasattr(M, "incrementar"):
            M.incrementar(f"storage_{op}")
    except Exception:
        pass
