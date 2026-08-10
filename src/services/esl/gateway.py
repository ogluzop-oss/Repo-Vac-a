"""
ESLGateway — puente DEGRADABLE con el sistema de etiquetas electrónicas (mismo patrón que
`utils/rfid_gateway.LectorZebraGateway`: `modo_simulado` sin hardware/credenciales, HTTP real cuando hay
endpoint + credencial del proveedor).

En modo REAL delega en un ADAPTADOR por proveedor (`services/esl/proveedores`), que construye la petición
con el formato de cada fabricante (VusionCloud/SES-imagotag, REST genérico, …). El envío HTTP se hace por
un `transport` inyectable (por defecto `requests`), lo que permite probar los adaptadores SIN red ni coste.
NUNCA se marca una etiqueta como "actualizada" sin confirmación real (en real la confirma el código HTTP;
en simulado se documenta como simulado).
"""

import logging

logger = logging.getLogger("esl.gateway")


def _http_transport(metodo, url, headers, cuerpo):
    """Transporte HTTP real (degradable). Devuelve (status_code|None, texto)."""
    try:
        import requests
    except Exception:
        return None, "requests no disponible"
    try:
        r = requests.request(metodo, url, json=cuerpo, headers=headers, timeout=6)
        return r.status_code, (r.text or "")
    except Exception as e:
        return None, str(e)


class ESLGateway:
    def __init__(self, proveedor="simulado", endpoint=None, store_id=None,
                 credencial=None, modo_simulado=True, transport=None):
        self.proveedor = proveedor or "simulado"
        self.endpoint = (endpoint or "").strip() or None
        self.store_id = store_id
        self._credencial = credencial
        self._transport = transport   # inyectable (tests); None → HTTP real
        # Simulado si se pide explícito o si no hay endpoint al que empujar (no se inventa un envío real).
        self.modo_simulado = bool(modo_simulado or not self.endpoint)

    def _ctx(self):
        return {"endpoint": self.endpoint, "store_id": self.store_id, "credencial": self._credencial}

    def _adaptador(self):
        from src.services.esl.proveedores import obtener_adaptador
        return obtener_adaptador(self.proveedor)

    # ── envío de contenido a una etiqueta ────────────────────────────────────
    def push(self, label_id, datos):
        """Empuja el contenido (precio/nombre/plantilla) a la etiqueta `label_id`.
        Devuelve {'ok': bool, 'estado': 'actualizada'|'error', 'detalle': str}."""
        if self.modo_simulado:
            logger.debug("[ESL SIM] push %s ← %s", label_id, datos)
            return {"ok": True, "estado": "actualizada", "detalle": "simulado"}
        transporte = self._transport or _http_transport
        return self._adaptador().push(label_id, datos, self._ctx(), transporte)

    def localizar(self, label_id):
        """Hace parpadear la etiqueta para localizarla físicamente en el lineal."""
        if self.modo_simulado:
            logger.debug("[ESL SIM] blink %s", label_id)
            return {"ok": True, "detalle": "simulado"}
        transporte = self._transport or _http_transport
        return self._adaptador().localizar(label_id, self._ctx(), transporte)
