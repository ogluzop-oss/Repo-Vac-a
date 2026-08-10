"""
Canal Web · Proveedores de creación de web (Fase WEB-02). Registro provider-agnostic. Oficial = Hostinger
(PREPARADO, no operativo). Ningún proveedor real se ejecuta en esta fase.
"""

from src.services.comercio_digital.canal_web.proveedores.base import (
    EspecificacionWeb, ProveedorWeb)
from src.services.comercio_digital.canal_web.proveedores.hostinger import (
    PROVEEDOR_OFICIAL, HostingerProvider)

_REGISTRO = {"hostinger": HostingerProvider}


def proveedor(clave=PROVEEDOR_OFICIAL) -> ProveedorWeb:
    cls = _REGISTRO.get((clave or "").lower(), HostingerProvider)
    return cls()


def oficial() -> ProveedorWeb:
    return proveedor(PROVEEDOR_OFICIAL)


def listar() -> list:
    return [cls().descriptor() for cls in _REGISTRO.values()]


__all__ = ["EspecificacionWeb", "ProveedorWeb", "HostingerProvider", "PROVEEDOR_OFICIAL",
           "proveedor", "oficial", "listar"]
