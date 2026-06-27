"""
Integración Qt de la capa universal de escáner (Bloque 8.3).

`FiltroEscaner` es un event-filter que observa las pulsaciones de teclado (modo
keyboard-wedge: USB/Bluetooth HID, lectores industriales) y emite `codigo_escaneado`
cuando detecta una ráfaga terminada en Enter/Tab. Funciona con cualquier fabricante
(Zebra, Honeywell, Datalogic, Newland, Sunmi, Bluebird, Chainway) sin configuración
específica, en cualquier SO.

Diseño NO intrusivo: por defecto NO consume los eventos (deja que los campos de texto
sigan funcionando con normalidad), de modo que es puramente ADITIVO. La detección
scan-vs-tecleo se hace por temporización (`BufferEscaner`).

Uso:
    self._scan = instalar_escaner(self, self._on_codigo)   # self._on_codigo(str)
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QElapsedTimer, QEvent, QObject, Qt, pyqtSignal

from src.services.perifericos.escaner_universal import BufferEscaner

logger = logging.getLogger(__name__)


class FiltroEscaner(QObject):
    """Event-filter que emite `codigo_escaneado(str)` ante un escaneo wedge completo."""

    codigo_escaneado = pyqtSignal(str)

    def __init__(self, parent=None, umbral_ms: int = 60, longitud_min: int = 3,
                 consumir: bool = False):
        super().__init__(parent)
        self._buffer = BufferEscaner(umbral_ms=umbral_ms, longitud_min=longitud_min)
        self._reloj = QElapsedTimer()
        self._reloj.start()
        self._consumir = consumir

    def eventFilter(self, obj, ev):  # noqa: N802 (API Qt)
        try:
            if ev.type() == QEvent.Type.KeyPress:
                t = float(self._reloj.elapsed())
                if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                    codigo = self._buffer.pulsar("\n", t)
                else:
                    texto = ev.text()
                    codigo = self._buffer.pulsar(texto, t) if texto else None
                if codigo:
                    self.codigo_escaneado.emit(codigo)
                    if self._consumir:
                        return True
        except Exception as e:  # nunca romper la UI por el filtro
            logger.debug("FiltroEscaner: %s", e)
        return super().eventFilter(obj, ev)


def instalar_escaner(widget, callback=None, *, umbral_ms: int = 60,
                     longitud_min: int = 3, consumir: bool = False) -> FiltroEscaner:
    """Instala un `FiltroEscaner` en `widget`. Si se da `callback`, lo conecta.

    Devuelve el filtro (mantener una referencia para que no lo recoja el GC).
    """
    filtro = FiltroEscaner(widget, umbral_ms=umbral_ms, longitud_min=longitud_min,
                           consumir=consumir)
    if callback is not None:
        filtro.codigo_escaneado.connect(callback)
    widget.installEventFilter(filtro)
    return filtro
