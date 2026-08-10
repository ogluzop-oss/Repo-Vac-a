"""
Canal Web · Dominios · Contrato del Registrar Adapter (Adapter Pattern, provider-agnostic).

Un `RegistrarAdapter` traduce entre el Canal Web y la API de un registrador de dominios concreto
(Cloudflare Registrar / Namecheap / Porkbun / OVH / IONOS / GoDaddy / …). NO contiene lógica de negocio
del Canal Web ni toca la BD: solo busca/precia/compra/consulta/renueva/cancela dominios y prepara DNS/
HTTPS. Las credenciales llegan por `AdapterContext` (resueltas por `conexiones`, cifradas). Añadir un
proveedor = una subclase; el núcleo del Canal Web no cambia (N7).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# TLDs propuestos por defecto al buscar (el proveedor real puede ampliarlos).
TLDS_DEFECTO = (".com", ".es", ".net", ".shop", ".store", ".online", ".tienda")


@dataclass
class RegistrarContext:
    """Contexto opaco de ejecución (credenciales cifradas resueltas en runtime; sin objetos de dominio)."""
    id_empresa: str | None = None
    proveedor: str | None = None
    credenciales: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


class RegistrarAdapter(ABC):
    """Contrato único de un registrador de dominios. Traducción + transporte. Sin lógica de negocio."""

    codigo: str = "base"
    nombre: str = "Registrador"

    @abstractmethod
    def buscar(self, nombre: str, *, tlds=None, contexto: RegistrarContext | None = None) -> list:
        """Propuestas de dominio disponibles para `nombre`. → [{dominio, tld, disponible, precio, moneda}]."""

    @abstractmethod
    def precio(self, dominio: str, *, contexto: RegistrarContext | None = None) -> dict:
        """Precio de registro/renovación. → {dominio, precio, renovacion, moneda}."""

    @abstractmethod
    def comprar(self, dominio: str, *, titular: dict, contexto: RegistrarContext | None = None) -> dict:
        """Compra/registra el dominio. → {ok, referencia, dominio, fecha_expiracion, error}."""

    @abstractmethod
    def estado(self, dominio: str, *, contexto: RegistrarContext | None = None) -> dict:
        """Estado del dominio (registrado/expirado/…). → {estado, fecha_expiracion, ...}."""

    def renovar(self, dominio: str, *, contexto: RegistrarContext | None = None) -> dict:
        return {"ok": False, "motivo": "no soportado por el proveedor"}

    def cancelar(self, dominio: str, *, contexto: RegistrarContext | None = None) -> dict:
        return {"ok": False, "motivo": "no soportado por el proveedor"}

    # ── DNS / HTTPS (preparado; degradable si el proveedor no lo permite) ──
    def configurar_dns(self, dominio: str, registros: list, *,
                       contexto: RegistrarContext | None = None) -> dict:
        """Configura registros DNS (A/AAAA/CNAME/TXT). Si el proveedor no lo permite, devuelve las
        INSTRUCCIONES para el usuario. → {ok, aplicado, instrucciones}."""
        return {"ok": True, "aplicado": False,
                "instrucciones": [f"Configura {r.get('tipo')} {r.get('nombre', '@')} → {r.get('valor')}"
                                  for r in (registros or [])]}

    def activar_https(self, dominio: str, *, contexto: RegistrarContext | None = None) -> dict:
        """Activa HTTPS (certificado) si el proveedor lo permite. Degradable. → {ok, aplicado}."""
        return {"ok": True, "aplicado": False, "motivo": "el proveedor no automatiza HTTPS"}

    def descriptor(self) -> dict:
        return {"codigo": self.codigo, "nombre": self.nombre, "tipo": "registrar_adapter",
                "provider_agnostic": True}


__all__ = ["TLDS_DEFECTO", "RegistrarContext", "RegistrarAdapter"]
