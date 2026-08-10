"""
Motor de prioridades del SomaObserver (Fase 4). Clasifica la relevancia de un hallazgo para decidir
si merece interrumpir al usuario. Solo ALTA y CRÍTICA provocan auto-invocación (configurable).
"""

MUY_BAJA = "MUY_BAJA"
BAJA = "BAJA"
MEDIA = "MEDIA"
ALTA = "ALTA"
CRITICA = "CRITICA"

ORDEN = {MUY_BAJA: 0, BAJA: 1, MEDIA: 2, ALTA: 3, CRITICA: 4}

# Umbral por defecto para intervenir automáticamente.
UMBRAL_INTERVENCION = ALTA


def nivel(p) -> int:
    return ORDEN.get(str(p).upper(), 0)


def merece_intervencion(p, *, umbral=UMBRAL_INTERVENCION) -> bool:
    return nivel(p) >= nivel(umbral)


def desde_riesgo(riesgo) -> str:
    """Mapea un nivel de riesgo (BAJO/MEDIO/ALTO/CRITICO) a prioridad."""
    return {"BAJO": BAJA, "MEDIO": MEDIA, "ALTO": ALTA, "CRITICO": CRITICA,
            "ALTA": ALTA, "CRITICA": CRITICA, "MEDIA": MEDIA, "BAJA": BAJA}.get(
        str(riesgo).upper(), MEDIA)


def peor(*prioridades) -> str:
    mejor = MUY_BAJA
    for p in prioridades:
        if nivel(p) > nivel(mejor):
            mejor = p
    return mejor
