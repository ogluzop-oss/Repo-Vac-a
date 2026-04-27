from PyQt6.QtCore import QObject, pyqtSignal
import time


class RFIDWorker(QObject):
    """
    Hebra de ejecución secundaria para la monitorización continua de tags.
    Ubicación: src/utils/rfid_worker.py
    """

    # Señales para comunicarse con la Ventana Principal
    tag_leido = pyqtSignal(str)  # Envía el EPC encontrado
    error_ocurrido = pyqtSignal(str)  # Envía el mensaje de error
    status_cambiado = pyqtSignal(bool)  # Indica si está buscando o no

    def __init__(self, gateway):
        super().__init__()
        self.gateway = gateway
        self._ejecutando = False

    def detener(self):
        """Detiene el bucle de lectura."""
        self._ejecutando = False

    def run(self):
        """Bucle principal de escucha."""
        self._ejecutando = True
        self.status_cambiado.emit(True)

        print("[WORKER] Vigilante RFID iniciado...")

        while self._ejecutando:
            try:
                # Intentamos una lectura rápida (inventario de 1 ciclo)
                # Asumimos que tu gateway tiene un método 'leer_un_tag' o similar
                if hasattr(self.gateway, "leer_tag"):
                    epc = self.gateway.leer_tag()

                    if epc:
                        self.tag_leido.emit(epc)
                        # Pausa de cortesía para no leer el mismo tag 100 veces por segundo
                        time.sleep(1.5)

            except Exception as e:
                self.error_ocurrido.emit(str(e))
                self._ejecutando = (
                    False  # Paramos por seguridad si hay error de hardware
                )

            # Pequeño respiro para el procesador
            time.sleep(0.1)

        self.status_cambiado.emit(False)
        print("[WORKER] Vigilante RFID detenido.")
