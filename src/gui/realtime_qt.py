"""
Puente SSE → Qt (Fase 8, Punto 5) — adapta el `RealtimeClient` EXISTENTE (transporte SSE de la Fase 4) a
señales Qt seguras para hilos, para que cualquier pantalla se refresque en tiempo real SIN polling. NO crea
un segundo transporte ni un segundo cliente: envuelve el existente. Los eventos llegan en un hilo de red y se
re-emiten como señales Qt (que Qt entrega en el hilo de la UI), evitando tocar widgets desde el hilo de red.

Uso típico:
    puente = RealtimePrediccionBridge(base_url, token_provider)
    puente.prediccion_generada.connect(mi_pantalla.recargar)
    puente.modelo_degradado.connect(mi_pantalla.avisar_degradacion)
    puente.iniciar()
"""

from PyQt6.QtCore import QObject, pyqtSignal


class RealtimePrediccionBridge(QObject):
    """Re-emite los eventos del canal 'prediccion' como señales Qt. Degradable: si no hay servidor SSE, el
    cliente subyacente reintenta y no se emite nada (nunca simula eventos)."""

    evento = pyqtSignal(dict)                 # cualquier evento del canal
    prediccion_generada = pyqtSignal(dict)    # prediccion.generada
    modelo_degradado = pyqtSignal(dict)       # prediccion.modelo_degradado
    reentrenamiento_requerido = pyqtSignal(dict)   # prediccion.reentrenamiento_requerido
    modelo_activado = pyqtSignal(dict)        # prediccion.modelo_activado

    def __init__(self, base_url, token_provider, parent=None):
        super().__init__(parent)
        self._cliente = None
        try:
            from src.services.eventbus.realtime_client import RealtimeClient
            self._cliente = RealtimeClient(base_url, token_provider, canales=["prediccion"],
                                           on_event=self._on_event)
        except Exception:
            self._cliente = None              # entorno sin cliente/red → puente inerte (no rompe la UI)

    def _on_event(self, ev):
        try:
            self.evento.emit(ev)
            tipo = (ev or {}).get("tipo", "")
            if tipo == "prediccion.generada":
                self.prediccion_generada.emit(ev)
            elif tipo == "prediccion.modelo_degradado":
                self.modelo_degradado.emit(ev)
            elif tipo == "prediccion.reentrenamiento_requerido":
                self.reentrenamiento_requerido.emit(ev)
            elif tipo == "prediccion.modelo_activado":
                self.modelo_activado.emit(ev)
        except Exception:
            pass

    def iniciar(self):
        if self._cliente:
            self._cliente.connect()

    def detener(self):
        if self._cliente:
            self._cliente.disconnect()
