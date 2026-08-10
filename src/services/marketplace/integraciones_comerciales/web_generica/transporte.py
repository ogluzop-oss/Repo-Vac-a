"""
Conector Web tradicional · TRANSPORTE HTTP (Modo B, REST). Cliente REAL contra los endpoints de la PROPIA web
del cliente (contrato REST documentado: ``GET/PUT /productos``, ``GET /pedidos``). Auth **Bearer** sobre
HTTPS. Errores → tipos canónicos del motor WEB-13. INYECTABLE (`set_transporte`) — costura para pruebas /
implementaciones alternativas.

SIN COSTES: no llama a ninguna API de terceros de pago; únicamente a la web del propio cliente (su servidor).
Degradable: sin URL/token, el adaptador no está `disponible()` y NO se hace ninguna petición.
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.web_generica.transporte")

TIMEOUT_DEFECTO = int(os.getenv("WEB_REST_TIMEOUT", "30"))
_TRANSPORTE = None


class TransporteWebRest:
    """Transporte HTTP real (requests) contra el contrato REST de la web del cliente."""

    def __init__(self, timeout=TIMEOUT_DEFECTO):
        self.timeout = timeout

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        import requests
        url = base_url.rstrip("/") + "/" + str(path).lstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="web_rest")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="web_rest")
        if r.status_code in (401, 403):
            raise IntegracionError(CodigoError.AUTH_ERROR, "token/permisos de la web", plataforma="web_rest")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="web_rest")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="web_rest",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteWebRest":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteWebRest()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, base_url, path, *, token, json, params)`)."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
