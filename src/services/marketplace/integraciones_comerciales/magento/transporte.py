"""
Conector Magento · TRANSPORTE HTTP (Fase WEB-18). Cliente REAL contra la Magento 2 REST API (`/rest/V1/…`)
con cabecera `Authorization: Bearer {token}`. Errores → tipos canónicos del motor WEB-13. INYECTABLE
(`set_transporte`) — costura para pruebas/impl. alternativas.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.magento.transporte")

API_VERSION = os.getenv("MAGENTO_API_VERSION", "V1")
TIMEOUT_DEFECTO = int(os.getenv("MAGENTO_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteMagento:
    """Transporte HTTP real (requests) para la Magento 2 REST API."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        url = f"{base_url.rstrip('/')}/rest/{self.api_version}/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "Authorization": f"Bearer {token or ''}"}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="magento")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="magento")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="magento")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos Magento", plataforma="magento")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="magento")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="magento",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteMagento":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteMagento()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
