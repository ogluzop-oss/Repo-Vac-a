"""
Cloud · Service Discovery distribuido (Fase VI · Bloque 11). Descubre NODOS remotos sobre el Node
Registry y los cruza con el Service Registry lógico (`src.platform.registry`): qué servicios podría
atender cada nodo. Preparación: hoy resuelve el registro en memoria; mañana, nodos remotos reales.
"""

from __future__ import annotations

from src.platform import registry as _svc
from src.platform.cloud import nodes


def nodos_en_region(region) -> list:
    return nodes.listar(region=region)


def nodo(nombre):
    return nodes.obtener(nombre)


def servicios_del_nodo(nombre) -> list:
    """Servicios lógicos que un nodo podría atender (todos los del Service Registry, preparado
    para asignación por nodo cuando el despliegue sea real)."""
    if not nodes.obtener(nombre):
        return []
    return _svc.nombres()


def localizar_servicio_en_nodos(nombre_servicio) -> list:
    """Nodos vivos que exponen un servicio (hoy: todos los disponibles; preparado para mapeo real)."""
    if _svc.obtener(nombre_servicio) is None:
        return []
    return [n.nombre for n in nodes.disponibles()]


def topologia() -> dict:
    """Vista topológica: regiones → nodos, y servicios registrados."""
    regiones = {}
    for n in nodes.listar():
        regiones.setdefault(n.region, []).append(n.nombre)
    return {"regiones": regiones, "nodos": len(nodes.listar()),
            "servicios": _svc.nombres()}


__all__ = ["nodos_en_region", "nodo", "servicios_del_nodo", "localizar_servicio_en_nodos",
           "topologia"]
