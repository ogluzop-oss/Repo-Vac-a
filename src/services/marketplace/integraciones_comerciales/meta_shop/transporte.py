"""
Conector Meta Shop · TRANSPORTE HTTP. Cliente REAL contra la Meta Graph API (Commerce Catalog),
autenticado con `access_token` como parámetro de consulta (igual que el resto de llamadas Graph).
Errores → tipos canónicos del motor WEB-13. INYECTABLE (`set_transporte`) para pruebas.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.meta_shop.transporte")

API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")
DEFAULT_HOST = os.getenv("META_GRAPH_API_HOST", "https://graph.facebook.com")
TIMEOUT_DEFECTO = int(os.getenv("META_SHOP_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteMetaShop:
    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        host = (base_url or DEFAULT_HOST).rstrip("/")
        url = f"{host}/{self.api_version}/{str(path).lstrip('/')}"
        qp = {**(params or {}), "access_token": token or ""}
        try:
            r = requests.request(method, url, json=json, params=qp, timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="meta_shop")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="meta_shop")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="meta_shop")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos Meta Shop",
                                   plataforma="meta_shop")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="meta_shop")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="meta_shop",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteMetaShop":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteMetaShop()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
