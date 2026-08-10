"""
Global SaaS · Deployment Model (Fase VI · Bloque 13). Modela los modos de despliegue soportados:
Cloud, On-Premise, Hybrid y Edge. PREPARADO: describe capacidades por modo sin modificar la lógica
de la app (el mismo núcleo funciona en cualquiera). Reutiliza el Cloud (nodos) y Resiliencia (edge).
"""

from __future__ import annotations

MODOS = ("cloud", "on_premise", "hybrid", "edge")

_CAPACIDADES = {
    "cloud":      {"multi_region": True, "gestionado": True, "escala_automatica": True, "edge": False},
    "on_premise": {"multi_region": False, "gestionado": False, "escala_automatica": False, "edge": False},
    "hybrid":     {"multi_region": True, "gestionado": True, "escala_automatica": True, "edge": True},
    "edge":       {"multi_region": True, "gestionado": True, "escala_automatica": False, "edge": True},
}

_ACTUAL = {"modo": "cloud"}


def modos() -> tuple:
    return MODOS


def fijar_modo(modo) -> bool:
    if modo not in MODOS:
        return False
    _ACTUAL["modo"] = modo
    try:
        from src.services.saas_global import configuracion_global
        configuracion_global.set("modelo_despliegue", modo)
    except Exception:
        pass
    return True


def modo_actual() -> str:
    return _ACTUAL["modo"]


def capacidades(modo=None) -> dict:
    return dict(_CAPACIDADES.get(modo or _ACTUAL["modo"], {}))


def descriptor() -> dict:
    return {"modos": list(MODOS), "actual": _ACTUAL["modo"],
            "capacidades": {m: _CAPACIDADES[m] for m in MODOS}}


__all__ = ["MODOS", "modos", "fijar_modo", "modo_actual", "capacidades", "descriptor"]
