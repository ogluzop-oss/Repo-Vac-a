"""
Conector PrestaShop · TRANSPORTE HTTP (Fase WEB-17). Cliente REAL contra el PrestaShop Webservice
(`/api/{recurso}`) con autenticación por API Key (HTTP Basic: key como usuario, contraseña vacía) y
`output_format=JSON`. Errores → tipos canónicos del motor WEB-13. INYECTABLE (`set_transporte`).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.prestashop.transporte")

TIMEOUT_DEFECTO = int(os.getenv("PRESTASHOP_TIMEOUT", "30"))
_TRANSPORTE = None


class TransportePresta:
    """Transporte HTTP real (requests) para el PrestaShop Webservice."""

    def __init__(self, timeout=TIMEOUT_DEFECTO):
        self.timeout = timeout

    def request(self, method, base_url, path, *, api_key=None, json=None, params=None):
        import requests
        url = base_url.rstrip("/") + "/api/" + str(path).lstrip("/")
        p = dict(params or {})
        p.setdefault("output_format", "JSON")
        try:
            r = requests.request(method, url, auth=(api_key, ""), json=json, params=p, timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="prestashop")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="prestashop")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="prestashop")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "API Key/permisos PrestaShop",
                                   plataforma="prestashop")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="prestashop")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="prestashop",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransportePresta":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransportePresta()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, api_key, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
