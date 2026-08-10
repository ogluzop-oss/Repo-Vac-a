"""
Adaptador Hostinger · TRANSPORTE HTTP (Fase WEB-14). Cliente HTTP REAL contra la API oficial de Hostinger.
Mapea los fallos de red/HTTP a los tipos de error canónicos del motor WEB-13 (`motor.errores`). Es
INYECTABLE (`set_transporte`) — costura para pruebas/impl. alternativas — igual que otros seams del ERP.

No contiene credenciales: el token se pasa por llamada (resuelto por el SecretManager). Sin token, el
adaptador ni siquiera llega aquí (devuelve MISSING_CREDENTIALS).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.hostinger.transporte")

BASE_URL_ENV = "HOSTINGER_API_URL"
DEFAULT_BASE_URL = "https://developers.hostinger.com/api"   # configurable por entorno
TIMEOUT_DEFECTO = int(os.getenv("HOSTINGER_TIMEOUT", "30"))

_TRANSPORTE = None


class TransporteHostinger:
    """Transporte HTTP real (requests). Errores → `IntegracionError` con código canónico."""

    def __init__(self, base_url=None, timeout=TIMEOUT_DEFECTO):
        self.base_url = base_url or os.getenv(BASE_URL_ENV) or DEFAULT_BASE_URL
        self.timeout = timeout

    def request(self, method, path, *, token=None, json=None, params=None) -> dict:
        import requests
        url = self.base_url.rstrip("/") + "/" + str(path).lstrip("/")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.request(method, url, headers=headers, json=json, params=params,
                                 timeout=self.timeout)
        except requests.Timeout as e:
            raise IntegracionError(CodigoError.TIMEOUT, str(e), plataforma="hostinger")
        except requests.ConnectionError as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="hostinger")
        except Exception as e:
            raise IntegracionError(CodigoError.NETWORK_ERROR, str(e), plataforma="hostinger")
        if r.status_code == 401:
            raise IntegracionError(CodigoError.AUTH_ERROR, "no autorizado", plataforma="hostinger")
        if r.status_code == 429:
            raise IntegracionError(CodigoError.RATE_LIMIT, "límite de peticiones", plataforma="hostinger")
        if r.status_code >= 400:
            raise IntegracionError(CodigoError.API_ERROR, f"HTTP {r.status_code}", plataforma="hostinger",
                                   detalle=(r.text or "")[:300])
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}


def get_transporte() -> "TransporteHostinger":
    global _TRANSPORTE
    if _TRANSPORTE is None:
        _TRANSPORTE = TransporteHostinger()
    return _TRANSPORTE


def set_transporte(transporte) -> None:
    """Inyecta un transporte (objeto con `request(method, path, *, token, json, params)`). Costura de test/
    impl. alternativa. NO cambia la arquitectura del motor."""
    global _TRANSPORTE
    _TRANSPORTE = transporte


def reset_transporte() -> None:
    set_transporte(None)
