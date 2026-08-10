"""
PCD · Canales · Conector REST real (Etapa B · Fase B2). Primer adaptador con TRANSPORTE REAL (HTTP)
sobre el Channel Adapter Framework. Genérico y PROVIDER-AGNOSTIC: los marketplaces concretos
(WooCommerce/Shopify/…) serán subclases que solo cambian el mapeo/rutas; el dominio no cambia.

Cumple la cadena obligatoria: Dominio → Adaptador → Servicio externo (nunca Dominio → API externa).
  · Sin lógica de negocio: solo traduce y transporta.
  · Credenciales/endpoint llegan por el `AdapterContext` (resueltos por `conexiones`, Fase B1).
  · Degradación elegante: sin endpoint → no realiza llamadas.
  · Transporte inyectable (`transporte`) para pruebas deterministas sin red externa.
"""

from __future__ import annotations

import logging

from src.services.comercio_digital.canales.adaptador import AdapterContext, ChannelAdapter

logger = logging.getLogger("cd.canales.rest")


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"_texto": getattr(resp, "text", "")}


class RestChannelAdapter(ChannelAdapter):
    """Adaptador REST genérico. `ruta_push`/`ruta_pull` se combinan con el endpoint base de la
    conexión. `transporte` permite inyectar un cliente HTTP (por defecto `requests`)."""

    version = "1.0.0"
    capacidades_soportadas = ("push", "pull", "webhook")

    def __init__(self, canal="rest", *, transporte=None, ruta_push="", ruta_pull="", timeout=10):
        self.canal = canal
        self._transporte = transporte
        self._ruta_push = ruta_push
        self._ruta_pull = ruta_pull
        self._timeout = timeout

    # ── traducción pura (identidad; los conectores concretos redefinen el mapeo) ──
    def traducir_saliente(self, mensaje: dict) -> dict:
        return dict(mensaje or {})

    def traducir_entrante(self, payload: dict) -> dict:
        return dict(payload or {})

    # ── transporte real (HTTP) ──
    def _http(self):
        if self._transporte is not None:
            return self._transporte
        import requests
        return requests

    def _url(self, contexto: AdapterContext, ruta):
        base = (contexto.extra or {}).get("endpoint_base") or ""
        if not base:
            return None
        return base.rstrip("/") + ("/" + ruta.lstrip("/") if ruta else "")

    def _headers(self, contexto: AdapterContext):
        cred = contexto.credenciales or {}
        tipo = (contexto.extra or {}).get("tipo_auth")
        h = {"Content-Type": "application/json"}
        if tipo == "apikey" and (cred.get("api_key") or cred.get("token")):
            h["Authorization"] = f"Bearer {cred.get('api_key') or cred.get('token')}"
        elif tipo == "basic" and cred.get("usuario"):
            import base64
            tok = base64.b64encode(f"{cred.get('usuario')}:{cred.get('password','')}".encode()).decode()
            h["Authorization"] = f"Basic {tok}"
        return h

    def enviar(self, externo: dict, *, contexto: AdapterContext) -> dict:
        url = self._url(contexto, self._ruta_push)
        if not url:
            return {"ok": False, "degradado": True, "motivo": "sin endpoint (conexión no configurada)"}
        try:
            r = self._http().post(url, json=externo, headers=self._headers(contexto),
                                  timeout=self._timeout)
            ok = 200 <= int(getattr(r, "status_code", 0)) < 300
            return {"ok": ok, "status": getattr(r, "status_code", None), "respuesta": _safe_json(r)}
        except Exception as e:
            logger.warning("REST enviar (%s): %s", self.canal, e)
            return {"ok": False, "error": str(e)}

    def recibir(self, *, contexto: AdapterContext) -> list:
        url = self._url(contexto, self._ruta_pull)
        if not url:
            return []
        params = {}
        cursor = (contexto.extra or {}).get("cursor")
        if cursor:
            params["since"] = cursor
        try:
            r = self._http().get(url, params=params, headers=self._headers(contexto),
                                 timeout=self._timeout)
            data = _safe_json(r)
            if isinstance(data, dict):
                return data.get("items", data.get("data", []))
            return data or []
        except Exception as e:
            logger.warning("REST recibir (%s): %s", self.canal, e)
            return []

    def descriptor(self) -> dict:
        d = super().descriptor()
        d.update({"tipo": "rest", "transporte_real": True, "provider_agnostic": True})
        return d


__all__ = ["RestChannelAdapter"]
