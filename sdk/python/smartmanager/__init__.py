"""
Smart Manager AI — SDK oficial de Python.

Cliente ligero para la Enterprise REST API (`/api/v1`). Sin dependencias obligatorias (usa la
biblioteca estándar `urllib`; si `requests` está instalado, no es necesario). Autenticación por JWT
(`token`) o API Key (`api_key` + `empresa`). Soporta la convención de paginación/orden/filtrado de la
API (`limit/offset/cursor/page/page_size/sort/order/filters`) y la iteración transparente por cursor.

    from smartmanager import Client
    c = Client("https://api.tu-dominio/api/v1", token=ACCESS)
    c.communications.list(limit=20, sort="fecha", order="desc")
    for item in c.contacts.paginate(q="ana"):
        ...

La fuente de verdad de la API es su OpenAPI (`/api/v1/openapi.json`); este SDK no duplica la lógica.
"""

from __future__ import annotations

import json as _json
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.0.0"

__all__ = ["Client", "Resource", "SmartManagerError", "__version__"]


class SmartManagerError(Exception):
    """Error de la API o de transporte. `status` y `payload` cuando estén disponibles."""

    def __init__(self, mensaje, *, status=None, payload=None):
        super().__init__(mensaje)
        self.status = status
        self.payload = payload


class Resource:
    """Recurso REST genérico (`/communications`, `/templates`, ...). Métodos CRUD mínimos."""

    def __init__(self, client: "Client", path: str):
        self._client = client
        self._path = path

    def list(self, **params):
        """GET de la colección. Acepta los parámetros de la convención (limit/offset/sort/...)."""
        return self._client.request("GET", self._path, params=params)

    def get(self, rid, **params):
        return self._client.request("GET", f"{self._path}/{rid}", params=params)

    def create(self, data):
        return self._client.request("POST", self._path, json=data)

    def paginate(self, **params):
        """Itera TODOS los elementos siguiendo `next_cursor` (convención de paginación de la API).
        Fuerza el sobre estándar activando `limit`. Cede elementos de uno en uno."""
        params.setdefault("limit", 100)
        while True:
            resp = self._client.request("GET", self._path, params=params)
            if isinstance(resp, dict) and "data" in resp:
                for item in resp.get("data") or []:
                    yield item
                cursor = resp.get("next_cursor")
                if not cursor:
                    return
                params["cursor"] = cursor
            else:                       # respuesta legacy (lista simple): sin más páginas
                for item in resp or []:
                    yield item
                return


# Recursos oficiales de la Enterprise REST API v1.
_RECURSOS = {
    "communications": "/communications",
    "conversations": "/conversations",
    "templates": "/templates",
    "campaigns": "/campaigns",
    "contacts": "/contacts",
    "audit": "/audit/events",
    "commerce": "/commerce",
    "system": "/system",
}


class Client:
    """Cliente de la Enterprise REST API. Provider-agnostic: `base_url` configurable. Transporte
    inyectable para pruebas: `transporte(method, url, params, json, headers) -> (status, dict)`."""

    __version__ = __version__

    def __init__(self, base_url, *, token=None, api_key=None, empresa=None, transporte=None,
                 timeout=20):
        self.base_url = str(base_url or "").rstrip("/")
        self.token = token
        self.api_key = api_key
        self.empresa = empresa
        self._transporte = transporte
        self._timeout = timeout
        for nombre, ruta in _RECURSOS.items():
            setattr(self, nombre, Resource(self, ruta))

    # ── cabeceras de autenticación (reutiliza el esquema de la API: JWT o API Key) ──
    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json",
             "User-Agent": f"smartmanager-python/{__version__}"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        elif self.api_key:
            h["X-API-Key"] = self.api_key
        if self.empresa:
            h["X-Empresa-Id"] = str(self.empresa)
        return h

    def _url(self, path, params=None):
        url = self.base_url + path
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        return url

    def request(self, method, path, *, params=None, json=None):
        """Ejecuta una petición y devuelve el cuerpo JSON (o lista). Lanza `SmartManagerError`."""
        headers = self._headers()
        # Transporte inyectado (pruebas / clientes alternativos): sin red real.
        if self._transporte is not None:
            status, cuerpo = self._transporte(method, self._url(path, params), params, json, headers)
            if status is not None and status >= 400:
                raise SmartManagerError(f"HTTP {status}", status=status, payload=cuerpo)
            return cuerpo
        datos = _json.dumps(json).encode("utf-8") if json is not None else None
        req = urllib.request.Request(self._url(path, params), data=datos, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                bruto = r.read().decode("utf-8") or "null"
                return _json.loads(bruto)
        except urllib.error.HTTPError as e:
            payload = None
            try:
                payload = _json.loads(e.read().decode("utf-8"))
            except Exception:
                pass
            raise SmartManagerError(f"HTTP {e.code}", status=e.code, payload=payload) from e
        except urllib.error.URLError as e:
            raise SmartManagerError(f"error de red: {e.reason}") from e

    def health(self):
        """Salud del servicio (endpoint público)."""
        return self.request("GET", "/system/health")
