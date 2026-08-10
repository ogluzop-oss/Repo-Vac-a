"""
Web Portal (Fase V · Bloque 2) — ARQUITECTURA del portal web empresarial.

Frontend DESACOPLADO que consume EXCLUSIVAMENTE la REST API / GraphQL (nunca SQL). Define los tipos
de portal (cliente/proveedor/transportista/empleado/asesoría/auditor), sus funcionalidades y sus
SCOPES de acceso (RBAC), y la sesión con tenant del token. Reutiliza OAuth/JWT/MFA y la auditoría.

    from src.services import portal
    portal.funcionalidades("cliente")
    s = portal.SesionPortal("cliente", token=jwt)
    portal.acceso.puede("cliente", "pedidos")
"""

from src.services.portal.portales import (  # noqa: F401
    TIPOS, FUNCIONALIDADES, SCOPES, funcionalidades, scopes, descriptor,
)
from src.services.portal.sesion_portal import SesionPortal  # noqa: F401
from src.services.portal import acceso  # noqa: F401

__all__ = ["TIPOS", "FUNCIONALIDADES", "SCOPES", "funcionalidades", "scopes", "descriptor",
           "SesionPortal", "acceso"]
