"""
BancaGateway — puente DEGRADABLE con la entidad bancaria (open banking / PSD2).

En modo REAL delega en un adaptador por proveedor (`proveedores/`) que consulta la API del agregador y
normaliza los movimientos. El transporte HTTP es inyectable (por defecto `requests`) para poder probar sin
red. Modo SIMULADO (sin endpoint/credencial): devuelve 0 movimientos — NUNCA inventa movimientos bancarios
(regla de honestidad: no se falsea dinero en el libro). Los movimientos reales se importan luego al motor de
conciliación existente.
"""

import logging

logger = logging.getLogger("banca.gateway")


def _http_transport(metodo, url, headers, params):
    """Transporte HTTP real (degradable). Devuelve (status_code|None, texto)."""
    try:
        import requests
    except Exception:
        return None, "requests no disponible"
    try:
        r = requests.request(metodo, url, headers=headers, params=params, timeout=8)
        return r.status_code, (r.text or "")
    except Exception as e:
        return None, str(e)


class BancaGateway:
    def __init__(self, proveedor="simulado", endpoint=None, account_id=None, credencial=None,
                 modo_simulado=True, transport=None):
        self.proveedor = proveedor or "simulado"
        self.endpoint = (endpoint or "").strip() or None
        self.account_id = account_id
        self._credencial = credencial
        self._transport = transport
        self.modo_simulado = bool(modo_simulado or not self.endpoint)

    def _ctx(self):
        return {"endpoint": self.endpoint, "account_id": self.account_id, "credencial": self._credencial}

    def obtener_movimientos(self, desde=None, hasta=None):
        """Lista de movimientos [{fecha, importe, concepto, referencia}]. Simulado → []."""
        if self.modo_simulado:
            logger.debug("[BANCA SIM] sin conexión real: 0 movimientos")
            return []
        from src.services.banca_online.proveedores import obtener_adaptador
        transporte = self._transport or _http_transport
        return obtener_adaptador(self.proveedor).obtener_movimientos(self._ctx(), desde, hasta, transporte)
