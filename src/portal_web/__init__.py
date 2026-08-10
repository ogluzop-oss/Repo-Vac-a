"""
Portal Web para Empleados (Back Office) — Fase WEB-04. Módulo INDEPENDIENTE del Canal Web y del Portal Cliente.
Versión web del ecosistema Smart Manager para empleados: reutiliza EXACTAMENTE los servicios/db/RBAC/
Entitlements/JWT/auditoría/eventos/StorageProvider/SecretManager existentes (N7, nunca duplica lógica).

Estado: **arquitectura PREPARADA** (navegación + acceso + layout + sesión + router REST mínimo que consume las
APIs existentes). No es ecommerce, no sustituye al escritorio/TPV, no incluye TPV/Caja web ni pagos online.
Multiempresa por `id_empresa`/`id_tienda` (nunca por dominio). Preparado para reutilizarse por la app móvil.
"""

from src.portal_web import acceso, layout, navegacion, sesion  # noqa: F401


def descriptor() -> dict:
    return navegacion.descriptor()


__all__ = ["navegacion", "acceso", "layout", "sesion", "descriptor"]
