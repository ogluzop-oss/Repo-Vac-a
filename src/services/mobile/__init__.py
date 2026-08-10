"""
Mobile Platform (Fase V · Bloque 1) — ARQUITECTURA oficial para apps móviles (Android/iOS).

NO es una app comercial: es la plataforma que consume EXCLUSIVAMENTE la REST API oficial (nunca SQL
ni servicios internos directos). Capas: core · networking · auth · sync (offline-first) · push ·
sesión. API-First. Reutiliza JWT/OAuth/MFA (`src.seguridad`), notificaciones (CCP) y el offline_store
de Resiliencia. Multiempresa (tenant del token).

    from src.services import mobile
    cli = mobile.ClienteMovil(base_url="/api/v1")     # habla REST
    mobile.auth.login(usuario, password)              # OAuth/JWT
    mobile.sync.encolar("pedido", {...})              # offline-first
"""

from src.services.mobile.core import CAPACIDADES, PLATAFORMAS, descriptor  # noqa: F401
from src.services.mobile.networking import ClienteMovil, base_api  # noqa: F401
from src.services.mobile import auth, push, sesion, sync  # noqa: F401

__all__ = ["CAPACIDADES", "PLATAFORMAS", "descriptor", "ClienteMovil", "base_api",
           "auth", "push", "sesion", "sync"]
