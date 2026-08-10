"""
Interfaz de transporte (Fase 4, SUBFASE 4.1). NO acopla a un unico protocolo: define el
contrato que cumplen los transportes concretos (local/LAN/VPN/Internet/Cloud/Edge). Asi, al
cambiar de transporte, el resto de la plataforma (motor, replicacion, ACK) no cambia.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ResultadoTransporte:
    ok: bool
    bytes: int = 0
    detalle: str = ""


class Transporte(ABC):
    nombre = "base"

    @abstractmethod
    def disponible(self, destino_tienda, id_empresa=None) -> bool:
        """True si la terminal destino es alcanzable por este transporte."""

    @abstractmethod
    def enviar(self, paquete: dict, destino_tienda, id_empresa=None) -> ResultadoTransporte:
        """Entrega fisicamente el paquete a la terminal destino. Devuelve el resultado."""

    def recibir(self, id_empresa=None) -> list:
        """Paquetes recibidos pendientes de aplicar (opcional segun transporte)."""
        return []
