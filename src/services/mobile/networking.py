"""
Mobile · Networking (Fase V · Bloque 1). Cliente REST de la plataforma móvil. Habla EXCLUSIVAMENTE
con la REST API oficial (`src.api`), nunca con SQL ni con servicios internos. En proceso usa el
test-client de Flask (consumo REST real, verificable); en la app nativa sería HTTP sobre el mismo
contrato. Propaga el JWT (Authorization: Bearer) → aislamiento multiempresa por token.
"""

from __future__ import annotations

import json

BASE = "/api/v1"


def base_api() -> str:
    return BASE


class ClienteMovil:
    """Cliente REST móvil. `token` = JWT del usuario (tenant del token). DEGRADABLE: si Flask no
    está disponible, `solicitar` devuelve un descriptor de la llamada preparada (sin ejecutar)."""

    def __init__(self, base_url=BASE, token=None):
        self.base_url = base_url
        self.token = token
        self._cli = None
        try:
            from src.api import crear_app
            self._cli = crear_app().test_client()
        except Exception:
            self._cli = None

    def _headers(self):
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def solicitar(self, metodo, ruta, *, params=None, cuerpo=None):
        """Realiza una llamada REST. Devuelve {status, json|texto}."""
        if not ruta.startswith("/"):
            ruta = f"{self.base_url}/{ruta}"
        if self._cli is None:
            return {"preparada": True, "metodo": metodo, "ruta": ruta}
        fn = getattr(self._cli, metodo.lower())
        resp = fn(ruta, headers=self._headers(), query_string=params or None,
                  data=json.dumps(cuerpo) if cuerpo is not None else None,
                  content_type="application/json")
        try:
            datos = resp.get_json()
        except Exception:
            datos = resp.get_data(as_text=True)
        return {"status": resp.status_code, "json": datos}

    def get(self, ruta, **kw):
        return self.solicitar("GET", ruta, **kw)

    def post(self, ruta, **kw):
        return self.solicitar("POST", ruta, **kw)


__all__ = ["BASE", "base_api", "ClienteMovil"]
