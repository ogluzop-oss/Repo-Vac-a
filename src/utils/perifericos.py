# src/utils/perifericos.py
"""Manejo de periféricos (impresoras, escáneres, cajón de dinero). Abstrae diferencias entre SO."""
import logging
import platform

logger = logging.getLogger(__name__)
OS = platform.system()


# ============================================================
# BLOQUE DETECCIÓN DE IMPRESORA TÉRMICA
# ============================================================

def detectar_impresora_termica() -> str | None:
    """Detecta impresora térmica conectada y devuelve su identificador."""
    try:
        if OS == "Windows":
            import usb.core
            dev = usb.core.find(idVendor=0x04B8, idProduct=0x0202)
            return dev.serial_number if dev else None
        elif OS == "Linux":
            import os as _os
            for device in _os.listdir("/dev"):
                if device.startswith("lp"):
                    return f"/dev/{device}"
        elif OS == "Darwin":
            import usb.core
            dev = usb.core.find(idVendor=0x04B8, idProduct=0x0202)
            return dev.serial_number if dev else None
    except Exception as e:
        logger.error(f"Error detectando impresora: {e}")
    return None


# ============================================================
# BLOQUE CONTROL DE CAJÓN DE DINERO
# ============================================================

def abrir_cajon_dinero():
    """Envía comando ESC/POS para abrir el cajón portamonedas."""
    try:
        from escpos.printer import Serial
        puerto  = "COM1" if OS == "Windows" else "/dev/ttyUSB0"
        printer = Serial(puerto)
        printer.cashdraw(2)
        printer.close()
        logger.info("Cajón de dinero abierto.")
    except Exception as e:
        logger.error(f"Error abriendo cajón: {e}")


# ============================================================
# BLOQUE LECTURA DE CÓDIGOS DE ESCÁNER
# ============================================================

def escanear_codigo() -> str | None:
    """Lee un código desde el escáner serie y lo devuelve como cadena."""
    try:
        import serial
        ser  = serial.Serial("COM3" if OS == "Windows" else "/dev/ttyACM0", 9600)
        data = ser.readline().decode().strip()
        ser.close()
        return data
    except Exception as e:
        logger.error(f"Error escaneando: {e}")
    return None
