"""
Conector Amazon · TRANSPORTE HTTP (Fase WEB-20). Cliente REAL contra la Amazon Selling Partner API (SP-API)
con cabecera `x-amz-access-token`. Errores → tipos canónicos del motor WEB-13. INYECTABLE (`set_transporte`).

Nota: la SP-API de producción exige además firma AWS SigV4 + LWA (OAuth). Aquí queda la estructura
operativa-ready; el resto es bloqueo externo (credenciales/partner), degradable — sin falsear conexiones.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.amazon.transporte")

DEFAULT_HOST = os.getenv("AMAZON_SPAPI_HOST", "https://sellingpartnerapi-eu.amazon.com")
API_VERSION = os.getenv("AMAZON_API_VERSION", "SP-API")
TIMEOUT_DEFECTO = int(os.getenv("AMAZON_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteAmazon:
    """Transporte HTTP real (requests) para la Amazon SP-API."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        host = (base_url or DEFAULT_HOST).rstrip("/")
        url = host + "/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "x-amz-access-token": token or ""}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="amazon")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="amazon")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="amazon")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos Amazon SP-API",
                                   plataforma="amazon")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="amazon")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="amazon",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteAmazon":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteAmazon()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
