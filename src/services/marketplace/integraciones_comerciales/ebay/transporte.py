"""
Conector eBay · TRANSPORTE HTTP (Fase WEB-21). Cliente REAL contra las eBay Sell APIs
(`/sell/{api}/v1/…`) con OAuth2 Bearer token. Errores → tipos canónicos del motor WEB-13. INYECTABLE
(`set_transporte`).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.ebay.transporte")

DEFAULT_HOST = os.getenv("EBAY_API_HOST", "https://api.ebay.com")
API_VERSION = os.getenv("EBAY_API_VERSION", "Sell v1")
TIMEOUT_DEFECTO = int(os.getenv("EBAY_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteEbay:
    """Transporte HTTP real (requests) para las eBay Sell APIs."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        host = (base_url or DEFAULT_HOST).rstrip("/")
        url = host + "/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "Authorization": f"Bearer {token or ''}"}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="ebay")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="ebay")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="ebay")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos eBay", plataforma="ebay")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="ebay")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="ebay",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteEbay":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteEbay()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
