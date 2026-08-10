"""
PCD · Canales · Channel Adapter Framework (CD-001/002/005 · Fase 6).

Infraestructura para conectar CUALQUIER canal futuro mediante adaptadores de TRADUCCIÓN PURA (N5).
En esta fase se entrega SOLO la infraestructura: contrato del adaptador, catálogo de plugins cargados
e integración con el Marketplace existente. NO se implementa ningún conector real.

Responsabilidades y límites:
  · Mantiene un CATÁLOGO de adaptadores cargados (registro de plugins de canal, no de servicios).
  · Cada adaptador publica ÚNICAMENTE su Service Contract (`contrato()`); registrar/descubrir/enrutar
    servicios es responsabilidad EXCLUSIVA de la Enterprise Platform.
  · Los plugins se instalan desde el Marketplace existente (capacidad), nunca un sistema paralelo.
  · Dirección Dominio → Adaptador → Canal. Los adaptadores no conocen el dominio ni mueven stock ni
    crean reservas ni consultan Availability/Fulfillment.
"""

from __future__ import annotations

import logging

from src.services.comercio_digital.canales.adaptador import (  # noqa: F401
    AdapterContext, ChannelAdapter, ReferenceAdapter,
)
from src.services.comercio_digital.canales.rest_adapter import RestChannelAdapter  # noqa: F401

logger = logging.getLogger("cd.canales")

FASE = 6

# Catálogo de adaptadores cargados: canal → instancia. Es un registro de PLUGINS, no de servicios.
_CATALOGO: dict = {}


def registrar_adaptador(adapter: ChannelAdapter) -> str:
    """Carga un adaptador en el catálogo de plugins. Valida el contrato mínimo."""
    if not isinstance(adapter, ChannelAdapter):
        raise TypeError("el adaptador debe implementar ChannelAdapter")
    if not getattr(adapter, "canal", ""):
        raise ValueError("el adaptador debe declarar 'canal'")
    _CATALOGO[adapter.canal] = adapter
    logger.debug("adaptador de canal cargado: %s", adapter.canal)
    return adapter.canal


def desregistrar(canal: str) -> bool:
    return _CATALOGO.pop(canal, None) is not None


def obtener(canal: str) -> ChannelAdapter | None:
    return _CATALOGO.get(canal)


def adaptadores() -> list:
    return sorted(_CATALOGO)


def contratos_adaptadores() -> list:
    """Service Contracts de los adaptadores cargados (para que los REGISTRE la Enterprise Platform)."""
    return [a.contrato() for a in _CATALOGO.values()]


def instalar_plugin(clave: str, *, id_empresa=None, usuario=None) -> dict:
    """Instala un plugin de canal desde el Marketplace EXISTENTE (capacidad). No crea sistema paralelo.
    Degradable: si el Marketplace no está disponible, informa sin fallar."""
    try:
        from src.platform import capabilities as cap
        mk = cap.marketplace()
        if mk is None or not hasattr(mk, "instalar"):
            return {"ok": False, "motivo": "marketplace no disponible"}
        return mk.instalar(clave, id_empresa=id_empresa, usuario=usuario)
    except Exception as e:
        logger.error("instalar_plugin(%s): %s", clave, e)
        return {"ok": False, "motivo": str(e)}


def catalogo_plugins(id_empresa=None, *, categoria="canal") -> list:
    """Plugins de canal disponibles en el Marketplace existente (capacidad, degradable)."""
    try:
        from src.platform import capabilities as cap
        mk = cap.marketplace()
        if mk is None or not hasattr(mk, "catalogo"):
            return []
        return mk.catalogo(id_empresa=id_empresa, categoria=categoria)
    except Exception:
        return []


def descriptor() -> dict:
    return {"servicio": "cd_canales", "rfc": "CD-001/002/005", "fase": FASE, "estado": "implementado",
            "framework": "channel_adapter", "contrato": "ChannelAdapter (traducción pura, N5)",
            "adaptadores_cargados": adaptadores(),
            "instalacion": "marketplace (capabilities)", "registra_servicios": False,
            "descubre_servicios": False, "enruta_servicios": False,
            "conoce_dominio": False, "mueve_stock": False}


__all__ = ["FASE", "AdapterContext", "ChannelAdapter", "ReferenceAdapter", "RestChannelAdapter",
           "registrar_adaptador", "desregistrar", "obtener", "adaptadores", "contratos_adaptadores",
           "instalar_plugin", "catalogo_plugins", "descriptor"]
