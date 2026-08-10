"""
Service Discovery (Fase IV · Bloque 3). Localiza servicios sobre el Service Registry: por nombre,
por capacidad, por transporte o por ruta. Preparado para registro automático (los subsistemas se
auto-registran vía `platform.bootstrap`). Sin red: resuelve el registro en memoria.
"""

from __future__ import annotations

from src.platform import registry
from src.platform.versioning import Version


def encontrar(nombre):
    return registry.obtener(nombre)


def por_capacidad(capacidad) -> list:
    return [c for c in registry.listar() if capacidad in (c.capacidades or ())]


def por_transporte(transporte) -> list:
    return [c for c in registry.listar() if transporte in (c.transportes or ())]


def por_ruta(prefijo) -> list:
    return [c for c in registry.listar()
            if any(str(prefijo).startswith(r) or r.startswith(str(prefijo)) for r in (c.rutas or ()))]


def compatible(nombre, version_requerida) -> bool:
    """¿El servicio registrado satisface la versión requerida (SemVer, mismo Major y ≥)?"""
    c = registry.obtener(nombre)
    if not c:
        return False
    return Version.parse(c.version).compatible_con(version_requerida)


def resolver_dependencias(nombre) -> dict:
    """Devuelve el estado de las dependencias declaradas de un servicio (presente/ausente)."""
    c = registry.obtener(nombre)
    if not c:
        return {}
    return {dep: (registry.obtener(dep) is not None) for dep in (c.dependencias or ())}


__all__ = ["encontrar", "por_capacidad", "por_transporte", "por_ruta", "compatible",
           "resolver_dependencias"]
