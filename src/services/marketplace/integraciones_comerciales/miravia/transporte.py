"""
Conector Miravia · TRANSPORTE HTTP (Fase WEB-22). Cliente REAL contra la API abierta de Miravia con Access
Token (`Authorization: Bearer` + `X-Miravia-Access-Token`). Errores → tipos canónicos del motor WEB-13.
INYECTABLE (`set_transporte`) para pruebas/impl. alternativas.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.miravia.transporte")

DEFAULT_HOST = os.getenv("MIRAVIA_API_HOST", "https://api.miravia.es/rest")
API_VERSION = os.getenv("MIRAVIA_API_VERSION", "1.0")
TIMEOUT_DEFECTO = int(os.getenv("MIRAVIA_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteMiravia:
    """Transporte HTTP real (requests) para la API abierta de Miravia."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, api_version=None):
        self.timeout = timeout
        self.api_version = api_version or API_VERSION

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        host = (base_url or DEFAULT_HOST).rstrip("/")
        url = host + "/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "Authorization": f"Bearer {token or ''}", "X-Miravia-Access-Token": token or ""}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="miravia")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="miravia")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="miravia")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos Miravia", plataforma="miravia")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="miravia")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="miravia",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteMiravia":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteMiravia()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
