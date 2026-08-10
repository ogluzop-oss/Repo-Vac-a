"""
Portal · Tipos y configuración (Fase V · Bloque 2). Registro de los tipos de portal, sus
funcionalidades y sus SCOPES de acceso (mínimo privilegio por rol externo). Cada funcionalidad se
sirve por REST/GraphQL. Sin BD.
"""

from __future__ import annotations

TIPOS = ("cliente", "proveedor", "transportista", "empleado", "asesoria", "auditor")

# Funcionalidades del portal (todas sobre REST/GraphQL).
FUNCIONALIDADES = ("login", "dashboard", "pedidos", "facturas", "documentacion", "workflow",
                   "mensajeria", "ccp", "incidencias", "firma", "historial", "timeline", "agenda")

# Scopes de acceso por tipo de portal (RBAC de mínimo privilegio).
SCOPES = {
    "cliente": ("pedidos", "facturas", "documentacion", "ccp", "incidencias", "firma",
                "historial", "timeline", "agenda", "dashboard"),
    "proveedor": ("pedidos", "facturas", "documentacion", "ccp", "incidencias", "workflow",
                  "historial", "dashboard"),
    "transportista": ("pedidos", "documentacion", "incidencias", "timeline", "dashboard"),
    "empleado": ("workflow", "mensajeria", "ccp", "documentacion", "agenda", "timeline",
                 "incidencias", "dashboard"),
    "asesoria": ("facturas", "documentacion", "historial", "workflow", "dashboard"),
    "auditor": ("facturas", "documentacion", "historial", "workflow", "timeline", "dashboard"),
}


def funcionalidades(tipo) -> list:
    """Funcionalidades disponibles para un tipo de portal (según sus scopes)."""
    return [f for f in FUNCIONALIDADES if f == "login" or f in SCOPES.get(tipo, ())]


def scopes(tipo) -> tuple:
    return SCOPES.get(tipo, ())


def descriptor() -> dict:
    return {"tipos": list(TIPOS), "funcionalidades": list(FUNCIONALIDADES),
            "scopes": {t: list(s) for t, s in SCOPES.items()},
            "comunicacion": ["rest", "graphql"],
            "seguridad": ["oauth", "scopes", "mfa", "sesiones", "auditoria"]}


__all__ = ["TIPOS", "FUNCIONALIDADES", "SCOPES", "funcionalidades", "scopes", "descriptor"]
