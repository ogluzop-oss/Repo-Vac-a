"""
Conector Shopify · TRANSPORTE HTTP (Fase WEB-16). Cliente REAL contra la Shopify Admin REST API
(`/admin/api/{version}/…`) con cabecera `X-Shopify-Access-Token`. Errores → tipos canónicos del motor WEB-13.
INYECTABLE (`set_transporte`) — costura para pruebas/impl. alternativas.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.shopify.transporte")

API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
TIMEOUT_DEFECTO = int(os.getenv("SHOPIFY_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteShopify:
    """Transporte HTTP real (requests) para la Shopify Admin REST API."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        url = f"{base_url.rstrip('/')}/admin/api/{self.api_version}/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "X-Shopify-Access-Token": token or ""}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="shopify")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="shopify")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="shopify")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos Shopify", plataforma="shopify")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="shopify")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="shopify",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteShopify":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteShopify()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
