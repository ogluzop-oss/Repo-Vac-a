"""
Conector OpenCart · TRANSPORTE HTTP (Fase WEB-19). Cliente REAL contra el OpenCart REST API (extensión REST)
con API Key por cabecera (`X-Oc-Api-Key`). El prefijo de ruta REST es configurable (`OPENCART_REST_PREFIX`,
por defecto `api/rest`). Errores → tipos canónicos del motor WEB-13. INYECTABLE (`set_transporte`).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.opencart.transporte")

REST_PREFIX = os.getenv("OPENCART_REST_PREFIX", "api/rest")
TIMEOUT_DEFECTO = int(os.getenv("OPENCART_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteOpenCart:
    """Transporte HTTP real (requests) para el OpenCart REST API."""

    def __init__(self, timeout=TIMEOUT_DEFECTO, rest_prefix=None):
        self.timeout = timeout
        self.rest_prefix = rest_prefix or REST_PREFIX

    def request(self, method, base_url, path, *, api_key=None, json=None, params=None):
        import requests
        url = f"{base_url.rstrip('/')}/{self.rest_prefix.strip('/')}/" + str(path).lstrip("/")
        headers = {"Accept": "application/json", "X-Oc-Api-Key": api_key or ""}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="opencart")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="opencart")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="opencart")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "API Key/permisos OpenCart", plataforma="opencart")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="opencart")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="opencart",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteOpenCart":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteOpenCart()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, api_key, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
