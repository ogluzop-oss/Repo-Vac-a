"""
Niveles de prioridad de un evento (Fase 1). Base para las futuras reglas de
sincronizacion/distribucion (una CRITICA se propagara antes que una INFORMATIVA).
"""

CRITICA = "CRITICA"
ALTA = "ALTA"
MEDIA = "MEDIA"
BAJA = "BAJA"
INFORMATIVA = "INFORMATIVA"

TODAS = [CRITICA, ALTA, MEDIA, BAJA, INFORMATIVA]

# Orden de despacho (0 = mas urgente). Lo usaran las fases de sincronizacion.
ORDEN = {CRITICA: 0, ALTA: 1, MEDIA: 2, BAJA: 3, INFORMATIVA: 4}


def normalizar(prioridad) -> str:
    p = (prioridad or MEDIA).upper()
    return p if p in ORDEN else MEDIA
