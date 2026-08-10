"""
Mobile · Core (Fase V · Bloque 1). Configuración y capacidades de la plataforma móvil. Declara las
plataformas soportadas y las funcionalidades previstas (todas sobre la REST API oficial). Sin BD.
"""

from __future__ import annotations

PLATAFORMAS = ("android", "ios")

# Funcionalidades previstas → recurso REST oficial que las alimenta (nunca SQL).
CAPACIDADES = {
    "login": "/api/v1/auth/login",
    "dashboard": "/api/v1/system/health",
    "notificaciones": "/api/v1/notifications",
    "agenda": "/api/v1/agenda",
    "directorio": "/api/v1/contacts",
    "clientes": "/api/v1/customers",
    "proveedores": "/api/v1/suppliers",
    "pedidos": "/api/v1/orders",
    "stock": "/api/v1/stock",
    "incidencias": "/api/v1/incidents",
    "tareas": "/api/v1/tasks",
    "workflow": "/api/v1/workflow",
    "documentos": "/api/v1/documents",
    "ccp": "/api/v1/communications",
    "timeline": "/api/v1/timeline",
}

# Capas de la arquitectura móvil (contrato para la futura app nativa).
CAPAS = ("core", "networking", "auth", "sync", "cache_offline", "actualizaciones",
         "push", "sesion")

VERSION = "1.0.0"


def descriptor() -> dict:
    """Descriptor de la plataforma móvil (para el Service Registry / documentación)."""
    return {
        "version": VERSION,
        "plataformas": list(PLATAFORMAS),
        "capas": list(CAPAS),
        "capacidades": CAPACIDADES,
        "comunicacion": "rest",     # SIEMPRE REST API oficial; nunca SQL ni servicios internos
        "offline_first": True,
        "seguridad": ["oauth", "jwt", "refresh_token", "pin", "biometria", "mfa", "revocacion"],
    }


__all__ = ["PLATAFORMAS", "CAPACIDADES", "CAPAS", "VERSION", "descriptor"]
