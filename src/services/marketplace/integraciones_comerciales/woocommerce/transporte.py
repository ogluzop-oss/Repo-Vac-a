"""
Conector WooCommerce · TRANSPORTE HTTP (Fase WEB-15). Cliente REAL contra la WooCommerce REST API
(`/wp-json/wc/v3/…`) con autenticación Consumer Key/Secret (HTTP Basic sobre HTTPS). Errores → tipos
canónicos del motor WEB-13. INYECTABLE (`set_transporte`) — costura para pruebas/impl. alternativas.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.woocommerce.transporte")

TIMEOUT_DEFECTO = int(os.getenv("WOO_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteWoo:
    """Transporte HTTP real (requests) para la WooCommerce REST API."""

    def __init__(self, timeout=TIMEOUT_DEFECTO):
        self.timeout = timeout

    def request(self, method, base_url, path, *, ck=None, cs=None, json=None, params=None):
        import requests
        url = base_url.rstrip("/") + "/wp-json/wc/v3/" + str(path).lstrip("/")
        try:
            r = requests.request(method, url, auth=(ck, cs), json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="woocommerce")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="woocommerce")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="woocommerce")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "credenciales/permisos WooCommerce",
                                   plataforma="woocommerce")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="woocommerce")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="woocommerce",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteWoo":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteWoo()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, ck, cs, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
