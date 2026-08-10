"""
Estados del ciclo de vida de un evento (Fase 1). Los eventos NUNCA se eliminan: se
archivan. La maquina de estados es permisiva pero valida las transiciones basicas.
"""

CREADO = "CREADO"
PENDIENTE = "PENDIENTE"
PROCESANDOSE = "PROCESANDOSE"
PROCESADO = "PROCESADO"
REINTENTANDO = "REINTENTANDO"
ERROR = "ERROR"
CANCELADO = "CANCELADO"
ARCHIVADO = "ARCHIVADO"

TODOS = [CREADO, PENDIENTE, PROCESANDOSE, PROCESADO, REINTENTANDO, ERROR, CANCELADO, ARCHIVADO]

# Estados finales: no admiten mas transiciones (salvo archivar).
FINALES = {PROCESADO, CANCELADO, ARCHIVADO}

# Transiciones permitidas (origen -> destinos validos).
TRANSICIONES = {
    CREADO:        {PENDIENTE, PROCESANDOSE, CANCELADO, ARCHIVADO},
    PENDIENTE:     {PROCESANDOSE, CANCELADO, ARCHIVADO},
    PROCESANDOSE:  {PROCESADO, ERROR, REINTENTANDO},
    REINTENTANDO:  {PROCESANDOSE, ERROR, CANCELADO},
    ERROR:         {REINTENTANDO, CANCELADO, ARCHIVADO},
    PROCESADO:     {ARCHIVADO},
    CANCELADO:     {ARCHIVADO},
    ARCHIVADO:     set(),
}


def es_valido(estado) -> bool:
    return estado in TODOS


def puede_transicionar(actual, nuevo) -> bool:
    return nuevo in TRANSICIONES.get(actual, set())


def normalizar(estado) -> str:
    e = (estado or CREADO).upper()
    return e if e in TODOS else CREADO
