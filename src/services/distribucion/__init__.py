"""
Motor Corporativo de Distribucion y Sincronizacion (Fase 2).

Distribuye los eventos del Event Bus (Fase 1) entre las terminales de una misma empresa
(tiendas/central/almacenes...). Sincronizacion CRITICA (inmediata) o PROGRAMADA (ventana de
mantenimiento), con destinatarios automaticos, cola persistente, confirmaciones (ACK),
reintentos con backoff, resolucion de conflictos, versionado lateral y soporte offline.

NO modifica el funcionamiento del ERP: solo añade infraestructura de distribucion. Todo pasa
por el bus; ningun modulo se llama directamente.

Uso tipico (backend):
    from src.services import distribucion
    distribucion.tick()                     # drena bus + distribuye criticos + reintentos
    distribucion.estado.resumen()           # panel de estado
"""

from src.services.distribucion import (cola, conflictos, config,          # noqa: F401
                                       destinatarios, estado, motor,
                                       politicas, reintentos, terminales,
                                       versionado)
from src.services.distribucion.motor import (distribuir,                  # noqa: F401
                                             distribuir_criticos,
                                             distribuir_programados,
                                             procesar_eventos_pendientes,
                                             procesar_reintentos,
                                             sincronizar_terminal, tick)

__all__ = [
    "tick", "procesar_eventos_pendientes", "distribuir", "distribuir_criticos",
    "distribuir_programados", "procesar_reintentos", "sincronizar_terminal",
    "cola", "config", "conflictos", "destinatarios", "estado", "motor",
    "politicas", "reintentos", "terminales", "versionado",
]
