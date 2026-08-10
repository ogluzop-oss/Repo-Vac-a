"""
Banca online (open banking / PSD2) — conexión bancaria en vivo, DEGRADABLE.

Capas: `gateway.BancaGateway` (puente degradable), `proveedores` (adaptadores PSD2), `config` (conexión por
cuenta con credencial cifrada + fábrica del gateway), `sync` (descarga e importa movimientos al motor de
conciliación existente). Real cuando hay endpoint+credenciales del agregador; si no, simulado (0 movimientos,
sin inventar dinero). RBAC `banca.*`.
"""

from src.services.banca_online import config, sync
from src.services.banca_online.gateway import BancaGateway

__all__ = ["config", "sync", "BancaGateway"]
