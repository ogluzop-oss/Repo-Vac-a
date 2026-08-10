"""
Rastreo por proximidad RFID de un artículo concreto — API-First, sin PyQt.

Cuando el operario busca un artículo, el lector RFID de la PDA/MDE detecta su alarma
(etiqueta adhesiva RFID o tag duro EAS) y mide la INTENSIDAD DE SEÑAL: cuanto más se
acerca el trabajador, más fuerte es la señal. La GUI usa `leer_proximidad()` (0..100)
para modular un pitido intermitente que se acelera al acercarse y se vuelve constante
justo al lado del artículo.

Modo DEGRADABLE: si hay un `gateway` con `leer_rssi(epc)` real (dBm) se usa la señal
física; si no, se simula una aproximación progresiva realista (con ruido), de forma que
el comportamiento del pitido es demostrable sin hardware.
"""

import random
import time

# Umbrales de nivel (sobre proximidad 0..100).
NIVEL_LEJOS, NIVEL_MEDIO, NIVEL_CERCA, NIVEL_AQUI = "LEJOS", "MEDIO", "CERCA", "AQUI"


class RastreoRFID:
    """Sesión de rastreo de un artículo por su código/EPC.

    Uso (la GUI llama a `leer_proximidad()` en cada tick de un temporizador):
        r = RastreoRFID("EAN123", gateway=lector_opcional)
        prox = r.leer_proximidad()   # 0.0 .. 100.0
        nivel = r.nivel()            # LEJOS/MEDIO/CERCA/AQUI
        if r.localizado(): ...
    """

    # Mapeo dBm→proximidad: -80 dBm (lejos) .. -30 dBm (pegado).
    _RSSI_MIN = -80.0
    _RSSI_MAX = -30.0

    def __init__(self, codigo, nombre=None, *, gateway=None, epc=None,
                 duracion_sim=None, semilla=None):
        self.codigo = codigo
        self.nombre = nombre
        self.gateway = gateway
        self.epc = epc or codigo
        self._rnd = random.Random(semilla)
        # Duración simulada de la aproximación (s): tiempo que "tarda" el operario en llegar.
        self._dur = float(duracion_sim) if duracion_sim else self._rnd.uniform(6.0, 11.0)
        self._t0 = time.time()
        self._prox = 0.0          # valor suavizado (evita saltos bruscos del pitido)

    # ── lectura de señal ────────────────────────────────────────────────────────
    def _rssi_hardware(self):
        fn = getattr(self.gateway, "leer_rssi", None) if self.gateway else None
        if not callable(fn):
            return None
        try:
            return fn(self.epc)
        except Exception:
            return None

    def leer_proximidad(self):
        """Devuelve la proximidad actual 0..100 (mayor = más cerca del artículo)."""
        rssi = self._rssi_hardware()
        if rssi is not None:
            bruto = (float(rssi) - self._RSSI_MIN) / (self._RSSI_MAX - self._RSSI_MIN) * 100.0
        else:
            elapsed = time.time() - self._t0
            base = min(100.0, elapsed / self._dur * 100.0)
            bruto = base + self._rnd.uniform(-6.0, 6.0)
            if base >= 100.0:                # ya "encima": mantén señal máxima estable
                bruto = max(bruto, 96.0)
        bruto = max(0.0, min(100.0, bruto))
        # Suavizado exponencial para un pitido continuo y no errático.
        self._prox = self._prox * 0.4 + bruto * 0.6
        return self._prox

    # ── clasificación ───────────────────────────────────────────────────────────
    def nivel(self, prox=None):
        p = self._prox if prox is None else prox
        if p >= 95.0:
            return NIVEL_AQUI
        if p >= 70.0:
            return NIVEL_CERCA
        if p >= 40.0:
            return NIVEL_MEDIO
        return NIVEL_LEJOS

    def localizado(self):
        """True cuando el trabajador está justo al lado del artículo (señal máxima)."""
        return self._prox >= 95.0
