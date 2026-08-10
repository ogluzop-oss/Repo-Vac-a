"""
Portal · Acceso (Fase V · Bloque 2). Control de acceso por tipo de portal + auditoría. Comprueba si
un portal puede usar una funcionalidad (scope) y registra el acceso (reutiliza la auditoría/
observabilidad existente). No accede a la BD directamente.
"""

from __future__ import annotations

from src.services.portal import portales


def puede(tipo_portal, funcionalidad) -> bool:
    if funcionalidad == "login":
        return True
    return funcionalidad in portales.scopes(tipo_portal)


def filtrar(tipo_portal, funcionalidades) -> list:
    return [f for f in funcionalidades if puede(tipo_portal, f)]


def registrar_acceso(tipo_portal, funcionalidad, *, id_empresa=None, usuario=None) -> bool:
    """Auditoría del acceso al portal (reutiliza observabilidad/auditoría; degradable)."""
    try:
        from src.utils.observabilidad import registrar_evento
        registrar_evento("portal", f"{tipo_portal}:{funcionalidad}", usuario=usuario)
        return True
    except Exception:
        return False


__all__ = ["puede", "filtrar", "registrar_acceso"]
