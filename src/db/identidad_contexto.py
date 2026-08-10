"""
IOC v2 · Fachada de identidad para la CAPA DE DATOS (Bloque IV — diseño/preparación).

Objetivo: permitir que `db/*` resuelva identidad (empresa/tienda/almacén) SIN depender de `services/*`,
respetando estrictamente la dirección de dependencias (no invertir capas).

Mecanismo (Inversión de Dependencias, hecho correctamente):
- La capa de datos DEFINE aquí el contrato/registro de resolución.
- Por defecto resuelve con las funciones canónicas de `db.empresa` (comportamiento actual, sin cambios).
- La capa de servicios (IOC) puede INYECTAR en el arranque un resolver más rico mediante
  `registrar_resolver(...)`. Así `db/*` llama a esta fachada (db → db) y la fachada, si hay resolver
  inyectado, delega en IOC — sin que `db` importe `services`.

ESTADO: ADITIVO y NO CABLEADO. Ningún módulo `db/*` lo usa todavía. No cambia ningún comportamiento
hasta que, en la fase final de limpieza, se migren los seams de la capa de datos a esta fachada y/o se
registre un resolver IOC. Reversible por construcción (basta con no usarlo).
"""

import logging

logger = logging.getLogger("db.identidad_contexto")

# Resolver externo opcional (inyectado por la capa de servicios/IOC en el arranque). Debe exponer,
# como pato-tipado, los métodos: empresa_id(id_empresa=None), tienda_id(), tienda_id_int(), almacen_id().
_RESOLVER = None


def registrar_resolver(resolver) -> None:
    """Inyecta un resolver de identidad (p.ej. un adaptador IOC de la capa de servicios). Idempotente.
    Llamado UNA vez en el arranque por la capa superior; `db/*` nunca importa `services/*`."""
    global _RESOLVER
    _RESOLVER = resolver


def resolver_registrado() -> bool:
    return _RESOLVER is not None


def _canonico_empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return id_empresa


def empresa_id(id_empresa=None):
    """Empresa activa. Si hay resolver IOC inyectado, delega en él; si no, usa la resolución canónica
    de `db.empresa` (idéntica al comportamiento actual). Nunca lanza."""
    if _RESOLVER is not None:
        try:
            v = _RESOLVER.empresa_id(id_empresa)
            if v:
                return v
        except Exception as e:
            logger.debug("resolver.empresa_id: %s", e)
    return _canonico_empresa(id_empresa)


def tienda_id():
    if _RESOLVER is not None:
        try:
            return _RESOLVER.tienda_id()
        except Exception:
            pass
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def tienda_id_int():
    if _RESOLVER is not None:
        try:
            return _RESOLVER.tienda_id_int()
        except Exception:
            pass
    try:
        from src.db.empresa import tienda_actual_id_int
        return tienda_actual_id_int()
    except Exception:
        return 0


def almacen_id():
    if _RESOLVER is not None:
        try:
            return _RESOLVER.almacen_id()
        except Exception:
            pass
    try:
        from src.db.empresa import almacen_actual_id
        return almacen_actual_id()
    except Exception:
        return None
