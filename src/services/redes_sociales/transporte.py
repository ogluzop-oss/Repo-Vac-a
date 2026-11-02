"""
Transporte HTTP genérico para clientes de plataformas sociales (Meta/TikTok/YouTube/X). Mismo
patrón que `services.marketplace.integraciones_comerciales.tiktok_shop.transporte` (auditoría
previa): `requests.request` real, normaliza códigos HTTP a la taxonomía YA existente
(`CodigoError`/`IntegracionError`), inyectable (`set_transporte`/`reset_transporte`) para pruebas.
Un único transporte sirve a las cuatro plataformas porque todas son REST+JSON con Bearer token —
lo que cambia por plataforma son las URLs/parámetros, no el protocolo de transporte.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("redes_sociales.transporte")

TIMEOUT_DEFECTO = int(os.getenv("REDES_SOCIALES_TIMEOUT", "20"))
_TRANSPORTE = None


class TransporteRedesSociales:
    """Transporte HTTP real (requests) común a todas las plataformas sociales soportadas."""

    def __init__(self, timeout=TIMEOUT_DEFECTO):
        self.timeout = timeout

    def request(self, method, url, *, token=None, headers=None, json=None, params=None,
               data=None, plataforma=None):
        import requests
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        if token and "Authorization" not in hdrs:
            hdrs["Authorization"] = f"Bearer {token}"
        try:
            r = requests.request(method, url, headers=hdrs, json=json, params=params,
                                 data=data, timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma=plataforma)
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma=plataforma)
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma=plataforma)
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, f"token/permisos {plataforma or ''}",
                                   plataforma=plataforma, detalle=(r.text or "")[:300])
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones",
                                   plataforma=plataforma)
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}",
                                   plataforma=plataforma, detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteRedesSociales":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteRedesSociales()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, url, *, token, headers, json, params,
    data, plataforma)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
