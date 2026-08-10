"""
Politica de reintentos de distribucion (Fase 2). Backoff configurable por empresa
(por defecto 1min, 5min, 15min, 30min, 1h, 12h, 24h).
"""

from datetime import datetime, timedelta

from src.services.distribucion import config as _cfg


def escalado(id_empresa=None) -> list:
    return _cfg.reintentos_lista(id_empresa)


def siguiente(reintentos: int, id_empresa=None) -> datetime:
    """Momento del proximo intento segun el numero de reintentos ya realizados."""
    esc = escalado(id_empresa)
    idx = min(max(int(reintentos or 0), 0), len(esc) - 1)
    return datetime.now() + timedelta(seconds=esc[idx])


def agotado(reintentos: int, id_empresa=None) -> bool:
    """True si se han consumido todos los reintentos configurados."""
    return int(reintentos or 0) >= len(escalado(id_empresa))
