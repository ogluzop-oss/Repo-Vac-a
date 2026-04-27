# src/utils/perifericos.py
"""
Módulo para manejo de periféricos (impresoras, escáneres, cajón de dinero).
Abstrae diferencias entre sistemas operativos.
"""
import platform
from typing import Optional
import logging

logger = logging.getLogger(__name__)

OS = platform.system()


def detectar_impresora_termica() -> Optional[str]:
    """Detecta impresora térmica conectada."""
    try:
        if OS == "Windows":
            # Usar win32api o pyusb para detectar
            import usb.core

            dev = usb.core.find(idVendor=0x04B8, idProduct=0x0202)  # Ejemplo Epson
            return dev.serial_number if dev else None
        elif OS == "Linux":
            # Buscar en /dev/usb/lp*
            import os

            for device in os.listdir("/dev"):
                if device.startswith("lp"):
                    return f"/dev/{device}"
        elif OS == "Darwin":  # macOS
            # Usar IOKit o pyusb
            import usb.core

            dev = usb.core.find(idVendor=0x04B8, idProduct=0x0202)
            return dev.serial_number if dev else None
    except Exception as e:
        logger.error(f"Error detectando impresora: {e}")
    return None


def abrir_cajon_dinero():
    """Envía comando ESC/POS para abrir cajón."""
    try:
        from escpos.printer import Serial

        # Asumir puerto serial estándar
        puerto = "COM1" if OS == "Windows" else "/dev/ttyUSB0"
        printer = Serial(puerto)
        printer.cashdraw(2)  # Comando para cajón
        printer.close()
        logger.info("Cajón de dinero abierto.")
    except Exception as e:
        logger.error(f"Error abriendo cajón: {e}")


def escanear_codigo() -> Optional[str]:
    """Lee código de escáner (simulado por ahora)."""
    try:
        import serial

        ser = serial.Serial("COM3" if OS == "Windows" else "/dev/ttyACM0", 9600)
        data = ser.readline().decode().strip()
        ser.close()
        return data
    except Exception as e:
        logger.error(f"Error escaneando: {e}")
    return None
