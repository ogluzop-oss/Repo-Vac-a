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
- `sgtin.codificar_sgtin96(...)`/`decodificar_sgtin96(...)` — trama EPC SGTIN-96 (GS1 EPC Tag Data
  Standard) real, para serializar unidades de producto (EAN/GTIN + número de serie).
- `vinculacion.vincular_articulo(...)` — asistente de vinculación RFID del módulo Ubicación (pestaña
  RFID): EAN → serie → EPC → grabación física → lectura cruzada → persistencia en `ubicaciones`.
- `hardware.resolver_gateway(...)` — instancia el gateway ya configurado (IP/puerto/modo real o
  simulado) desde `db.rfid_hardware` — único punto que decide con qué lector se habla.
"""

from src.services.rfid.antihurto import (alarma_salida_no_pagada, marcar_pagado,
                                         registrar_guardia)
from src.services.rfid.hardware import resolver_gateway
from src.services.rfid.inventario import barrido_inventario
from src.services.rfid.localizador import RastreoRFID
from src.services.rfid.sgtin import codificar_sgtin96, decodificar_sgtin96
from src.services.rfid.vinculacion import vincular_articulo, vincular_lote

__all__ = ["barrido_inventario", "RastreoRFID", "alarma_salida_no_pagada", "marcar_pagado",
           "registrar_guardia", "codificar_sgtin96", "decodificar_sgtin96", "vincular_articulo",
           "vincular_lote", "resolver_gateway"]
