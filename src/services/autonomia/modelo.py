"""
Modelo de la Autonomia Supervisada (Paquete Enterprise 10). Estados de plan/accion, modos de
empresa y niveles. La IA propone, la organizacion decide, el sistema ejecuta solo lo autorizado.
"""

# Estados de un plan de ejecucion
BORRADOR = "BORRADOR"
PENDIENTE_APROBACION = "PENDIENTE_APROBACION"
APROBADO = "APROBADO"
EN_EJECUCION = "EN_EJECUCION"
EJECUTADO = "EJECUTADO"
PARCIAL = "PARCIAL"
CANCELADO = "CANCELADO"
REVERTIDO = "REVERTIDO"

# Estados de una accion
ACC_PENDIENTE = "PENDIENTE"
ACC_VALIDADA = "VALIDADA"
ACC_EJECUTADA = "EJECUTADA"
ACC_FALLIDA = "FALLIDA"
ACC_OMITIDA = "OMITIDA"
ACC_REVERTIDA = "REVERTIDA"

# Modos de empresa (SUBFASE 10.13) — cada modo limita las capacidades del sistema.
MODO_MANUAL = "MANUAL"          # el sistema NUNCA ejecuta; solo propone tareas a humanos
MODO_ASISTIDA = "ASISTIDA"      # ejecuta solo acciones informativas (avisos/tareas); resto se propone
MODO_SEMIAUTO = "SEMIAUTO"      # ejecuta acciones reversibles NO criticas, tras aprobacion
MODO_AVANZADA = "AVANZADA"      # ejecuta todas las reversibles tras aprobacion; criticas siempre gated

MODOS = (MODO_MANUAL, MODO_ASISTIDA, MODO_SEMIAUTO, MODO_AVANZADA)

# Nivel de "permisividad" de ejecucion por modo (para el indicador de autonomia y los limites).
_NIVEL_MODO = {MODO_MANUAL: 0, MODO_ASISTIDA: 1, MODO_SEMIAUTO: 2, MODO_AVANZADA: 3}


def nivel_modo(modo) -> int:
    return _NIVEL_MODO.get(str(modo).upper(), 1)
