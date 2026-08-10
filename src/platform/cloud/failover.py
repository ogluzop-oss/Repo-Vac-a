"""
Cloud · Failover (Fase VI · Bloque 11) — PREPARADO, sin activar. Modela los roles Primary →
Secondary → Recovery de un conjunto de nodos y calcula el plan de conmutación si el primario cae.
No ejecuta la conmutación (no hay red): deja la arquitectura lista. Reutiliza el Node Registry.
"""

from __future__ import annotations

from src.platform.cloud import heartbeat, nodes

PRIMARY, SECONDARY, RECOVERY = "primary", "secondary", "recovery"

# Asignación de roles por grupo lógico (en memoria; preparado para configuración real).
_ROLES: dict = {}     # grupo -> {rol: nombre_nodo}


def asignar_rol(grupo, rol, nombre_nodo) -> bool:
    if rol not in (PRIMARY, SECONDARY, RECOVERY):
        return False
    _ROLES.setdefault(grupo, {})[rol] = nombre_nodo
    return True


def roles(grupo) -> dict:
    return dict(_ROLES.get(grupo, {}))


def plan_conmutacion(grupo) -> dict:
    """Devuelve el plan de failover: quién asumiría si el primario no está vivo. NO conmuta."""
    r = _ROLES.get(grupo, {})
    primary = r.get(PRIMARY)
    activo = bool(primary) and heartbeat.vivo(primary) and \
        (nodes.obtener(primary).estado in (nodes.ALIVE, nodes.READY) if nodes.obtener(primary) else False)
    if activo:
        return {"grupo": grupo, "activo": primary, "conmutar": False}
    # Candidato de relevo: secondary vivo, si no recovery.
    for rol in (SECONDARY, RECOVERY):
        cand = r.get(rol)
        if cand and heartbeat.vivo(cand):
            return {"grupo": grupo, "activo": primary, "conmutar": True, "relevo": cand,
                    "rol_relevo": rol, "ejecutado": False}
    return {"grupo": grupo, "activo": primary, "conmutar": True, "relevo": None,
            "nota": "sin relevo disponible", "ejecutado": False}


__all__ = ["PRIMARY", "SECONDARY", "RECOVERY", "asignar_rol", "roles", "plan_conmutacion"]
