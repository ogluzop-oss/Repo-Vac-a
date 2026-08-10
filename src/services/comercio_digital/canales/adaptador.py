"""
PCD · Canales · Contrato del Channel Adapter (CD-001/002/005 · Fase 6).

Un adaptador de canal es un TRADUCTOR PURO entre el Dominio ERP y una API externa. Contrato único que
implementará cualquier canal futuro (WooCommerce, Shopify, Amazon, eBay, Miravia, TikTok Shop, Meta,
Prestashop, APIs externas…) — pero en esta fase NO se implementa ninguno real: solo la infraestructura.

Reglas del adaptador (N5, invariantes):
  · NO contiene lógica de negocio.
  · NO conoce el dominio, ni inventario, ni Workflow, ni Rules, ni IA, ni Availability, ni Fulfillment.
  · Únicamente traduce: Dominio ERP ⇄ API externa. Dirección Dominio → Adaptador → Canal.
    Nunca Canal → Dominio: en entrada, el adaptador SOLO devuelve datos traducidos hacia arriba; no
    invoca al dominio.
  · Publica ÚNICAMENTE su Service Contract. No registra/descubre/enruta servicios (eso es de la
    Enterprise Platform).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AdapterContext:
    """Contexto opaco de ejecución de un adaptador. Sin objetos de dominio."""
    id_empresa: str | None = None
    canal: str | None = None
    correlation_id: str | None = None
    credenciales: dict = field(default_factory=dict)   # las aporta la config del plugin (opaco)
    extra: dict = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Contrato único de un adaptador de canal. Traducción pura + transporte. Sin lógica de negocio."""

    canal: str = ""                       # identificador del canal (clave)
    version: str = "1.0.0"
    capacidades_soportadas: tuple = ()    # subconjunto de ("push", "pull", "webhook")

    # ── Contrato (lo ÚNICO que publica el adaptador; la plataforma lo registra) ──
    def contrato(self):
        from src.platform.contracts import ServiceContract
        return ServiceContract(
            nombre=f"cd_canal_{self.canal}", version=self.version,
            descripcion=f"Adaptador de canal {self.canal} (traducción pura, sin lógica de negocio)",
            capacidades=tuple(self.capacidades_soportadas), transportes=("eventbus",),
            dependencias=("comercio_digital",), rutas=())

    # ── Traducción pura (neutro de dominio ⇄ forma externa) ──
    @abstractmethod
    def traducir_saliente(self, mensaje: dict) -> dict:
        """Mensaje neutro del dominio → forma de la API externa. Sin lógica de negocio."""

    @abstractmethod
    def traducir_entrante(self, payload: dict) -> dict:
        """Forma de la API externa → mensaje neutro del dominio. Sin lógica de negocio."""

    # ── Transporte (sin red real en esta fase; lo implementan los plugins reales) ──
    def enviar(self, externo: dict, *, contexto: AdapterContext) -> dict:
        raise NotImplementedError("el transporte 'enviar' lo implementa cada plugin de canal")

    def recibir(self, *, contexto: AdapterContext) -> list:
        return []

    def descriptor(self) -> dict:
        return {"canal": self.canal, "version": self.version,
                "capacidades": list(self.capacidades_soportadas), "tipo": "channel_adapter"}


class ReferenceAdapter(ChannelAdapter):
    """Adaptador de REFERENCIA — SOLO INFRAESTRUCTURA, NO es un conector real ni un canal de negocio.

    Existe únicamente para validar el framework y el Sync Engine de extremo a extremo sin acoplarse a
    ningún proveedor ni realizar E/S de red. Traducción identidad y un "buzón" en memoria que simula el
    lado externo. No debe usarse en producción como canal."""

    canal = "referencia"
    version = "1.0.0"
    capacidades_soportadas = ("push", "pull", "webhook")

    def __init__(self):
        self._buzon: list = []            # simula el sistema externo (en memoria, infra)

    def traducir_saliente(self, mensaje: dict) -> dict:
        return {"externo": dict(mensaje or {})}

    def traducir_entrante(self, payload: dict) -> dict:
        return dict((payload or {}).get("externo", payload or {}))

    def enviar(self, externo: dict, *, contexto: AdapterContext) -> dict:
        self._buzon.append(externo)
        return {"ok": True, "ref": len(self._buzon)}

    def recibir(self, *, contexto: AdapterContext) -> list:
        return list(self._buzon)


__all__ = ["AdapterContext", "ChannelAdapter", "ReferenceAdapter"]
