"""
Rate limiting (A5.2) — limitador de peticiones por clave (IP/identidad/endpoint).

Backend **enchufable**: por defecto en memoria (suficiente para una instancia);
una arquitectura SaaS multi-instancia puede sustituirlo por Redis con
`set_backend(...)` **sin tocar la API pública** (`permitido`). Ventana fija simple.
"""

import threading
import time


class BackendMemoria:
    """Contador por ventana fija, en memoria del proceso (thread-safe)."""

    def __init__(self):
        self._datos = {}
        self._lock = threading.Lock()

    def golpear(self, clave: str, ventana_seg: int) -> int:
        ahora = time.time()
        with self._lock:
            inicio, cuenta = self._datos.get(clave, (ahora, 0))
            if ahora - inicio >= ventana_seg:
                inicio, cuenta = ahora, 0
            cuenta += 1
            self._datos[clave] = (inicio, cuenta)
            return cuenta

    def reset(self, clave: str = None):
        with self._lock:
            if clave is None:
                self._datos.clear()
            else:
                self._datos.pop(clave, None)


class BackendLimite:
    """Interfaz que debe cumplir un backend alternativo (p. ej. Redis)."""

    def golpear(self, clave: str, ventana_seg: int) -> int:  # pragma: no cover
        raise NotImplementedError


_backend = BackendMemoria()


def set_backend(backend):
    """Sustituye el backend (p. ej. uno basado en Redis para SaaS multi-instancia)."""
    global _backend
    _backend = backend


def backend():
    return _backend


def permitido(clave: str, limite: int, ventana_seg: int) -> bool:
    """True si la petición está dentro del límite; False si lo supera."""
    return _backend.golpear(clave, ventana_seg) <= limite
