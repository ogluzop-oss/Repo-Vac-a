"""
Estados de una declaración AEAT y su máquina de transiciones (FASE AEAT-1).

BORRADOR  → editable/regenerable.
GENERADO  → casillas calculadas y documento emitido (con hash).
PRESENTADO→ marcada como presentada ante AEAT (terminal salvo anulación).
ANULADO   → anulada (terminal).
"""

BORRADOR = "BORRADOR"
GENERADO = "GENERADO"
PRESENTADO = "PRESENTADO"
ANULADO = "ANULADO"

ESTADOS = (BORRADOR, GENERADO, PRESENTADO, ANULADO)

# Transiciones permitidas (origen → destinos).
TRANSICIONES = {
    BORRADOR: {GENERADO, ANULADO},
    GENERADO: {GENERADO, PRESENTADO, ANULADO},   # GENERADO→GENERADO = regeneración del borrador
    PRESENTADO: {ANULADO},
    ANULADO: set(),
}


def transicion_valida(actual: str, destino: str) -> bool:
    if actual is None:
        return destino in (BORRADOR, GENERADO)
    return destino in TRANSICIONES.get(actual, set())
