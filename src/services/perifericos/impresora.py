"""
Capa de adaptadores de impresora de tickets (Bloque 8.4 — preparación hardware).

Define una interfaz única multiplataforma y multifabricante para impresión de tickets,
con backends de conexión USB / Bluetooth / Red (TCP-IP) sobre `python-escpos` cuando está
disponible. NO requiere hardware para importarse ni para construir configuración: degrada
con gracia (estado PREPARADO) y solo intenta E/S real al imprimir.

Estado por defecto: **PREPARADO PARA VALIDACIÓN** — compatibilidad teórica vía ESC/POS
(estándar común a EPSON, Bixolon, Star en modo ESC/POS, Sunmi). La certificación real
requiere el dispositivo físico.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Conexiones soportadas por la capa.
USB = "usb"
BLUETOOTH = "bluetooth"
RED = "red"          # TCP-IP
SERIE = "serie"
CONEXIONES = (USB, BLUETOOTH, RED, SERIE)

# Fabricantes con compatibilidad teórica vía ESC/POS (perfil python-escpos).
FABRICANTES = {
    "epson":   {"escpos_profile": None,      "notas": "ESC/POS nativo (referencia)"},
    "bixolon": {"escpos_profile": None,      "notas": "ESC/POS compatible"},
    "star":    {"escpos_profile": "TSP100",  "notas": "ESC/POS en modo compatible; algunos modelos Star Line Mode"},
    "sunmi":   {"escpos_profile": None,      "notas": "ESC/POS integrado (dispositivos Android)"},
    "generico":{"escpos_profile": None,      "notas": "ESC/POS estándar"},
}


@dataclass
class ImpresoraConfig:
    """Configuración de una impresora de tickets. No abre conexión al crearse."""
    fabricante: str = "generico"
    conexion: str = USB
    # USB
    vendor_id: int | None = None
    product_id: int | None = None
    # Red (TCP-IP)
    host: str | None = None
    puerto: int = 9100
    # Serie / Bluetooth (puerto del SO)
    dispositivo: str | None = None
    baudios: int = 9600
    opciones: dict = field(default_factory=dict)

    def valida(self) -> tuple[bool, str]:
        if self.conexion not in CONEXIONES:
            return False, f"conexión no soportada: {self.conexion}"
        if self.conexion == USB and not (self.vendor_id and self.product_id):
            return False, "USB requiere vendor_id y product_id"
        if self.conexion == RED and not self.host:
            return False, "red requiere host"
        if self.conexion in (SERIE, BLUETOOTH) and not self.dispositivo:
            return False, f"{self.conexion} requiere 'dispositivo' (p. ej. COM3 / /dev/rfcomm0)"
        return True, "ok"


def backends_disponibles() -> dict:
    """Indica qué backends de E/S están instalados en este entorno (sin tocar hardware)."""
    estado = {USB: False, RED: False, SERIE: False, BLUETOOTH: False, "escpos": False}
    try:
        import escpos  # noqa: F401
        estado["escpos"] = True
        estado[RED] = True  # Network solo necesita socket
    except Exception:
        pass
    try:
        import usb.core  # noqa: F401
        estado[USB] = True
    except Exception:
        pass
    try:
        import serial  # noqa: F401
        estado[SERIE] = True
        estado[BLUETOOTH] = True  # BT SPP se expone como puerto serie del SO
    except Exception:
        pass
    return estado


def _crear_printer(cfg: ImpresoraConfig):
    """Crea el objeto python-escpos adecuado. Lanza si falta backend/hardware."""
    from escpos import printer as P
    if cfg.conexion == USB:
        return P.Usb(cfg.vendor_id, cfg.product_id, **cfg.opciones)
    if cfg.conexion == RED:
        return P.Network(cfg.host, port=cfg.puerto, **cfg.opciones)
    if cfg.conexion in (SERIE, BLUETOOTH):
        return P.Serial(cfg.dispositivo, baudrate=cfg.baudios, **cfg.opciones)
    raise ValueError(f"conexión no soportada: {cfg.conexion}")


def imprimir_lineas(lineas, cfg: ImpresoraConfig, *, cortar: bool = True) -> tuple[bool, str]:
    """Imprime una lista de líneas de texto. Devuelve (ok, mensaje).

    Degradable: si falta backend o hardware, devuelve (False, motivo) sin lanzar.
    No certifica el dispositivo; ejecuta la E/S real solo si todo está disponible.
    """
    ok, motivo = cfg.valida()
    if not ok:
        return False, f"Configuración inválida: {motivo}"
    try:
        printer = _crear_printer(cfg)
    except Exception as e:
        return False, f"Backend/dispositivo no disponible ({cfg.conexion}): {e}"
    try:
        for ln in (lineas or []):
            printer.text(f"{ln}\n")
        if cortar:
            try:
                printer.cut()
            except Exception:
                pass
        try:
            printer.close()
        except Exception:
            pass
        return True, "Impreso"
    except Exception as e:
        logger.error("Error imprimiendo: %s", e)
        return False, f"Error de impresión: {e}"


def estado_certificacion() -> dict:
    """Resumen para el informe de hardware: fabricantes, conexiones y backends."""
    return {
        "estado": "PREPARADO PARA VALIDACIÓN",
        "fabricantes": sorted(FABRICANTES.keys()),
        "conexiones": list(CONEXIONES),
        "backends_disponibles": backends_disponibles(),
        "nota": "Compatibilidad teórica vía ESC/POS; certificación real requiere hardware físico.",
    }
