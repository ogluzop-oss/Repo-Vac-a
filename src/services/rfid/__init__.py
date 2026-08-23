"""
Servicios RFID (API-First, sin PyQt) — capa de lógica reutilizable por la GUI y por
integraciones remotas. Degradables (patrón del ERP): usan un lector físico Zebra/RFD
(`src.utils.rfid_gateway.LectorZebraGateway`) si está disponible, o una simulación
realista si no hay hardware, de modo que TODO el flujo es demostrable ahora mismo.

- `inventario.barrido_inventario(...)` — barrido con PDA/MDE (RFID activo): detecta los
  artículos por sus alarmas (etiqueta adhesiva RFID o tag duro EAS) y devuelve el conteo
  detectado + las discrepancias frente al stock esperado.
- `localizador.RastreoRFID` — rastreo por proximidad de un artículo concreto (por código/
  EPC): expone `leer_proximidad()` (0..100) para el pitido de aproximación de la GUI.
- `antihurto.alarma_salida_no_pagada(...)` — manejador INTERNO de la alarma EAS/RFID de la puerta:
  al detectar la salida de un artículo sin pagar, envía un push al móvil del guardia con la ficha
  del artículo (sin frontend de escritorio; el único frontend es la app del guardia).
"""

from src.services.rfid.antihurto import alarma_salida_no_pagada, registrar_guardia
from src.services.rfid.inventario import barrido_inventario
from src.services.rfid.localizador import RastreoRFID

__all__ = ["barrido_inventario", "RastreoRFID", "alarma_salida_no_pagada", "registrar_guardia"]
