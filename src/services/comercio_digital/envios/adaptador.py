"""
PCD · Envíos · Contrato del Carrier Adapter (Etapa B · Fase B7).

Mismo patrón que los Channel Adapters, aplicado a transportistas (MRW/GLS/Correos/DHL/UPS/FedEx/Seur…):
traducción + transporte, SIN lógica de negocio, provider-agnostic y degradable. Cadena
Dominio → Adaptador → Servicio externo (nunca Dominio → API del transportista). Sustituir un
transportista por otro queda confinado a su adaptador + configuración.

Contrato mínimo:
  · crear_envio(envio, contexto) → {ok, tracking, etiqueta, referencia}
  · rastrear(tracking, contexto)  → {estado, eventos}
Las credenciales/endpoint llegan por el `AdapterContext` (resueltos por `conexiones`, Fase B1).
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod

from src.services.comercio_digital.canales.adaptador import AdapterContext  # reutiliza el contexto

logger = logging.getLogger("cd.envios.adaptador")


class CarrierAdapter(ABC):
    transportista: str = ""
    version: str = "1.0.0"

    def contrato(self):
        from src.platform.contracts import ServiceContract
        return ServiceContract(nombre=f"cd_carrier_{self.transportista}", version=self.version,
                               descripcion=f"Adaptador de transportista {self.transportista}",
                               capacidades=("crear_envio", "rastrear"), transportes=("eventbus",),
                               dependencias=("comercio_digital",), rutas=())

    @abstractmethod
    def crear_envio(self, envio: dict, *, contexto: AdapterContext) -> dict:
        """Crea el envío en el transportista y devuelve tracking + etiqueta."""

    @abstractmethod
    def rastrear(self, tracking: str, *, contexto: AdapterContext) -> dict:
        """Estado + eventos de seguimiento del envío."""

    def descriptor(self) -> dict:
        return {"transportista": self.transportista, "version": self.version, "tipo": "carrier"}


class SimuladoCarrier(CarrierAdapter):
    """Transportista de REFERENCIA (solo infra, degradable). Genera tracking/etiqueta deterministas
    sin red externa. No es un transportista de producción."""

    transportista = "simulado"

    def crear_envio(self, envio: dict, *, contexto: AdapterContext) -> dict:
        tracking = "SIMTRK-" + uuid.uuid4().hex[:12].upper()
        return {"ok": True, "tracking": tracking, "referencia": tracking,
                "etiqueta": f"https://envios.simulado.local/etiqueta/{tracking}.pdf",
                "estado": "etiquetado"}

    def rastrear(self, tracking: str, *, contexto: AdapterContext) -> dict:
        return {"estado": "en_transito",
                "eventos": [{"estado": "etiquetado", "detalle": "Etiqueta generada"},
                            {"estado": "en_transito", "detalle": "En reparto"}]}


class RestCarrierAdapter(CarrierAdapter):
    """Transportista REST genérico (transporte HTTP real, inyectable, degradable). Los transportistas
    concretos serán subclases que solo cambian rutas/mapeo."""

    def __init__(self, transportista="rest", *, transporte=None, ruta_envio="/shipments",
                 ruta_track="/track", timeout=10):
        self.transportista = transportista
        self._transporte = transporte
        self._ruta_envio = ruta_envio
        self._ruta_track = ruta_track
        self._timeout = timeout

    def _http(self):
        if self._transporte is not None:
            return self._transporte
        import requests
        return requests

    def _url(self, contexto, ruta):
        base = (contexto.extra or {}).get("endpoint_base")
        return (base.rstrip("/") + "/" + ruta.lstrip("/")) if base else None

    def _headers(self, contexto):
        cred = contexto.credenciales or {}
        h = {"Content-Type": "application/json"}
        if cred.get("api_key") or cred.get("token"):
            h["Authorization"] = f"Bearer {cred.get('api_key') or cred.get('token')}"
        return h

    def crear_envio(self, envio: dict, *, contexto: AdapterContext) -> dict:
        url = self._url(contexto, self._ruta_envio)
        if not url:
            return {"ok": False, "degradado": True, "motivo": "sin endpoint (conexión no configurada)"}
        try:
            r = self._http().post(url, json=envio, headers=self._headers(contexto),
                                  timeout=self._timeout)
            data = r.json() if hasattr(r, "json") else {}
            return {"ok": 200 <= getattr(r, "status_code", 0) < 300,
                    "tracking": data.get("tracking"), "referencia": data.get("id"),
                    "etiqueta": data.get("label_url")}
        except Exception as e:
            logger.warning("crear_envio REST (%s): %s", self.transportista, e)
            return {"ok": False, "error": str(e)}

    def rastrear(self, tracking: str, *, contexto: AdapterContext) -> dict:
        url = self._url(contexto, self._ruta_track)
        if not url:
            return {"estado": "desconocido", "eventos": []}
        try:
            r = self._http().get(url, params={"tracking": tracking}, headers=self._headers(contexto),
                                 timeout=self._timeout)
            data = r.json() if hasattr(r, "json") else {}
            return {"estado": data.get("estado", "desconocido"), "eventos": data.get("eventos", [])}
        except Exception as e:
            logger.warning("rastrear REST (%s): %s", self.transportista, e)
            return {"estado": "desconocido", "eventos": []}


__all__ = ["CarrierAdapter", "SimuladoCarrier", "RestCarrierAdapter"]
