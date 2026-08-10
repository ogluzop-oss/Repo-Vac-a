"""
Canal Web · Dominios — registro/fachada de registradores (Adapter Pattern, provider-agnostic).

Catálogo de registradores de dominios sobre el contrato `RegistrarAdapter`. Por defecto se usa el
proveedor `simulado` (degradable). Arquitectura preparada para Cloudflare Registrar / Namecheap /
Porkbun / OVH / IONOS / GoDaddy: se añaden con `registrar_adaptador(codigo, factory)` SIN tocar el
núcleo del Canal Web (N7). Las credenciales del proveedor se resuelven vía `conexiones` (cifradas,
Secret Manager); nunca en código. Multiempresa.
"""

from __future__ import annotations

import logging

from src.services.comercio_digital.dominios.adaptador import (  # noqa: F401
    TLDS_DEFECTO, RegistrarAdapter, RegistrarContext,
)

logger = logging.getLogger("cd.dominios")

# codigo → factory de adaptador
_PROVEEDORES: dict = {}
# Proveedores preparados (arquitectura lista; se activan al conectar credenciales reales).
PROVEEDORES_PREPARADOS = ("cloudflare", "namecheap", "porkbun", "ovh", "ionos", "godaddy")


def registrar_adaptador(codigo, factory) -> bool:
    """Registra un registrador de dominios (extensible; terceros pueden añadir el suyo)."""
    _PROVEEDORES[codigo] = factory
    return True


def disponibles() -> list:
    return sorted(_PROVEEDORES.keys())


def _proveedor_por_defecto() -> str:
    """Proveedor activo: el configurado por Rules/config o `simulado` (degradable)."""
    try:
        from src.platform import capabilities as cap
        rules = cap.rules()
        if rules is not None and hasattr(rules, "registrador_dominios"):
            p = rules.registrador_dominios()
            if p in _PROVEEDORES:
                return p
    except Exception:
        pass
    return "simulado"


def adaptador(codigo=None):
    """Instancia el adaptador del registrador indicado (o el por defecto). Degradable a `simulado`."""
    codigo = codigo or _proveedor_por_defecto()
    factory = _PROVEEDORES.get(codigo) or _PROVEEDORES.get("simulado")
    return factory() if factory else None


def contexto(id_empresa=None, proveedor=None) -> RegistrarContext:
    """Construye el contexto (credenciales cifradas del proveedor, resueltas por `conexiones`)."""
    prov = proveedor or _proveedor_por_defecto()
    cred = {}
    try:
        from src.services.comercio_digital import conexiones
        cred = conexiones.credenciales(f"dominios_{prov}", id_empresa=id_empresa) or {}
    except Exception:
        pass
    return RegistrarContext(id_empresa=id_empresa, proveedor=prov, credenciales=cred)


def descriptor() -> dict:
    return {"servicio": "comercio_digital.dominios", "proveedores": disponibles(),
            "preparados": list(PROVEEDORES_PREPARADOS), "por_defecto": _proveedor_por_defecto(),
            "provider_agnostic": True, "motor_nuevo": False,
            "operaciones": ["buscar", "precio", "comprar", "estado", "renovar", "cancelar",
                            "configurar_dns", "activar_https"]}


def _registrar_por_defecto():
    if "simulado" in _PROVEEDORES:
        return
    from src.services.comercio_digital.dominios.simulado import SimuladoRegistrar
    registrar_adaptador("simulado", SimuladoRegistrar)


_registrar_por_defecto()

__all__ = ["TLDS_DEFECTO", "RegistrarAdapter", "RegistrarContext", "PROVEEDORES_PREPARADOS",
           "registrar_adaptador", "disponibles", "adaptador", "contexto", "descriptor"]
