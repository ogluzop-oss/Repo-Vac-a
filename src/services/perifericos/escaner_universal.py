"""
Capa universal de lectura de códigos (BLOQUE 8 — Fase H).

Objetivo: el TPV recibe códigos de barras/QR sin importar el fabricante ni el bus,
en cualquier plataforma. La inmensa mayoría de escáneres (Zebra, Honeywell, Datalogic,
Newland, Sunmi, Bluebird, Chainway…) funcionan como *keyboard-wedge* (HID): "teclean"
el código y un terminador (Enter/Tab). Eso es portable a Windows/macOS/Linux/Android/iOS
sin drivers. Esta capa parsea ese flujo distinguiendo el escaneo (ráfaga rápida) del
tecleo manual (lento), y deja puntos de extensión para serie/USB/Bluetooth HID.

El núcleo (`BufferEscaner`) es lógica pura, sin Qt ni hardware → testeable y determinista.
La integración en el TPV se hace con un event filter de teclado que alimenta `pulsar()`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Terminadores típicos de un escáner wedge.
TERMINADORES = ("\n", "\r", "\t")

# Un escáner emite caracteres muy rápido (decenas de ms). Un humano, mucho más lento.
# Si el tiempo entre teclas supera este umbral, se considera tecleo manual y se reinicia.
UMBRAL_INTER_CHAR_MS = 60
# Longitud mínima para aceptar un código (evita falsos positivos de teclas sueltas).
LONGITUD_MIN = 3


class BufferEscaner:
    """Acumula pulsaciones y emite un código cuando llega un terminador tras una ráfaga.

    Uso (integración Qt): en keyPressEvent/eventFilter llamar a `pulsar(texto, t_ms)`.
    Si devuelve una cadena, es un código escaneado completo. Para detección por timing,
    pasar el timestamp en milisegundos; si no se pasa, se acepta cualquier ráfaga.
    """

    def __init__(self, umbral_ms: int = UMBRAL_INTER_CHAR_MS, longitud_min: int = LONGITUD_MIN):
        self._buffer: list[str] = []
        self._ultimo_t: float | None = None
        self._umbral = umbral_ms
        self._longitud_min = longitud_min

    def reset(self) -> None:
        self._buffer.clear()
        self._ultimo_t = None

    def pulsar(self, texto: str, t_ms: float | None = None) -> str | None:
        """Procesa una pulsación. Devuelve el código si se completó un escaneo, si no None.

        `texto` es el carácter (o terminador) recibido; `t_ms` el instante en ms (opcional).
        """
        if texto is None or texto == "":
            return None

        # Control de temporización: una pausa larga reinicia el buffer (tecleo humano).
        if t_ms is not None and self._ultimo_t is not None:
            if (t_ms - self._ultimo_t) > self._umbral:
                self._buffer.clear()
        self._ultimo_t = t_ms

        # ¿Es un terminador? -> intenta emitir.
        if texto in TERMINADORES:
            return self._emitir()

        # Acumula (un texto puede traer varios chars si el wedge inyecta en bloque).
        for ch in texto:
            if ch in TERMINADORES:
                cod = self._emitir()
                if cod is not None:
                    return cod
            else:
                self._buffer.append(ch)
        return None

    def _emitir(self) -> str | None:
        codigo = "".join(self._buffer).strip()
        self._buffer.clear()
        self._ultimo_t = None
        if len(codigo) >= self._longitud_min:
            logger.debug("Código escaneado: %s", codigo)
            return codigo
        return None


def normalizar_codigo(codigo: str | None) -> str | None:
    """Limpia un código leído (espacios, terminadores). Devuelve None si queda vacío."""
    if not codigo:
        return None
    c = codigo.strip().strip("".join(TERMINADORES))
    return c or None
