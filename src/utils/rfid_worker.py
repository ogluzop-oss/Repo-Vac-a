# src/utils/rfid_worker.py
import time

from PyQt6.QtCore import QObject, pyqtSignal

# ============================================================
# BLOQUE SEÑALES DE COMUNICACIÓN RFID
# ============================================================

class RFIDWorker(QObject):
    """Hebra de ejecución secundaria para la monitorización continua de tags."""

    tag_leido       = pyqtSignal(str)   # Envía el EPC encontrado
    error_ocurrido  = pyqtSignal(str)   # Envía el mensaje de error
    status_cambiado = pyqtSignal(bool)  # Indica si está buscando o no

    def __init__(self, gateway):
        super().__init__()
        self.gateway    = gateway
        self._ejecutando = False

    # ============================================================
    # BLOQUE CONTROL DEL HILO
    # ============================================================

    def detener(self):
        """Detiene el bucle de lectura."""
        self._ejecutando = False

    # ============================================================
    # BLOQUE LECTURA CONTINUA DE TAGS
    # ============================================================

    def run(self):
        """Bucle principal de escucha."""
        self._ejecutando = True
        self.status_cambiado.emit(True)
        print("[WORKER] Vigilante RFID iniciado...")

        while self._ejecutando:
            try:
                if hasattr(self.gateway, "leer_tag"):
                    epc = self.gateway.leer_tag()
                    if epc:
                        self.tag_leido.emit(epc)
                        time.sleep(1.5)
            except Exception as e:
                self.error_ocurrido.emit(str(e))
                self._ejecutando = False

            time.sleep(0.1)

        self.status_cambiado.emit(False)
        print("[WORKER] Vigilante RFID detenido.")
