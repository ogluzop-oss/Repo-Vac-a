"""
Cliente REUTILIZABLE de tiempo real en red (consume el endpoint SSE `/api/v1/realtime/stream`). Abstracción
ÚNICA para todos los módulos/futuras apps (TPV, Stock, CRM, Logística, Producción, GMAO, SAT, Calidad, Canal
Web, móvil): conectar/suscribir/desuscribir/reconectar/on_event/on_error, con reconexión por backoff
exponencial y reautenticación. NO duplica clientes por módulo.

Degradable: usa `requests` (ya dependencia del proyecto). Si no hay servidor SSE alcanzable, `on_error` se
invoca y el cliente reintenta; nunca simula eventos.
"""

import json
import logging
import threading
import time

logger = logging.getLogger("eventbus.realtime.client")


class RealtimeClient:
    def __init__(self, base_url, token_provider, *, canales=None, on_event=None, on_error=None,
                 max_reintentos=0, backoff_base=1.0, backoff_max=30.0):
        """`token_provider`: callable() → JWT vigente (se reevalúa en cada (re)conexión → reautenticación).
        `canales`: lista de canales (p. ej. ['stock','ventas']) o None (todos los del tenant).
        `on_event(dict)` y `on_error(exc)`: callbacks. `max_reintentos`=0 → ilimitado."""
        self._base = base_url.rstrip("/")
        self._token_provider = token_provider
        self._canales = ",".join(canales) if canales else None
        self._on_event = on_event or (lambda ev: None)
        self._on_error = on_error or (lambda e: None)
        self._max = max_reintentos
        self._b0 = backoff_base
        self._bmax = backoff_max
        self._activo = False
        self._hilo = None

    def connect(self):
        if self._activo:
            return
        self._activo = True
        self._hilo = threading.Thread(target=self._run, daemon=True, name="RealtimeClient")
        self._hilo.start()

    def disconnect(self):
        self._activo = False

    def subscribe(self, canales):
        """Cambia los canales (aplica en la próxima (re)conexión)."""
        self._canales = ",".join(canales) if canales else None

    def _url(self):
        u = f"{self._base}/api/v1/realtime/stream"
        return f"{u}?canales={self._canales}" if self._canales else u

    def _run(self):
        import requests
        intento = 0
        while self._activo:
            try:
                token = self._token_provider() if callable(self._token_provider) else self._token_provider
                with requests.get(self._url(), headers={"Authorization": f"Bearer {token}"},
                                  stream=True, timeout=(10, None)) as r:
                    if r.status_code != 200:
                        raise RuntimeError(f"SSE status {r.status_code}")
                    intento = 0                                   # conexión OK → reset backoff
                    self._leer(r)
            except Exception as e:
                self._on_error(e)
                intento += 1
                if self._max and intento >= self._max:
                    break
                time.sleep(min(self._b0 * (2 ** (intento - 1)), self._bmax))   # backoff exponencial

    def _leer(self, r):
        tipo = None
        for raw in r.iter_lines(decode_unicode=True):
            if not self._activo:
                break
            if raw is None:
                continue
            linea = raw.strip()
            if linea.startswith(":"):
                continue                                          # heartbeat/comentario
            if linea.startswith("event:"):
                tipo = linea[6:].strip()
            elif linea.startswith("data:"):
                dato = linea[5:].strip()
                try:
                    ev = json.loads(dato)
                except Exception:
                    ev = {"raw": dato}
                if tipo and isinstance(ev, dict):
                    ev.setdefault("tipo", tipo)
                self._on_event(ev)
                tipo = None
