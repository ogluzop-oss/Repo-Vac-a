"""
Framework de automatizaciones ENCADENADAS (Paquete Enterprise 4, SUBFASE 4.7). No cadenas fijas:
una cadena es una secuencia de PASOS (acciones del catalogo); los pasos con `requiere_aprobacion`
lanzan el Workflow/BPM existente y PAUSAN la cadena hasta la aprobacion humana.
"""

import logging

from src.services.automatizacion import acciones

logger = logging.getLogger("automatizacion.cadenas")

_CADENAS = {}


def definir(codigo, pasos) -> None:
    """pasos = [{'accion','params'?,'requiere_aprobacion'?}, ...]."""
    _CADENAS[codigo] = list(pasos)


def obtener(codigo):
    return _CADENAS.get(codigo)


def listar():
    return sorted(_CADENAS.keys())


def ejecutar(codigo, ctx=None, id_empresa=None, *, desde_paso=0) -> dict:
    pasos = _CADENAS.get(codigo, [])
    ctx = ctx or {}
    hechos = []
    for i in range(desde_paso, len(pasos)):
        paso = pasos[i]
        if paso.get("requiere_aprobacion"):
            r = acciones.solicitar_aprobacion(ctx, paso.get("params"), id_empresa)
            hechos.append({"paso": i, "accion": "solicitar_aprobacion", "estado": "PENDIENTE",
                           "resultado": r})
            return {"cadena": codigo, "estado": "PENDIENTE_APROBACION", "pasos": hechos,
                    "reanudar_en": i + 1}
        r = acciones.ejecutar(paso["accion"], ctx, paso.get("params"), id_empresa)
        hechos.append({"paso": i, "accion": paso["accion"], "estado": "EJECUTADO", "resultado": r})
    return {"cadena": codigo, "estado": "COMPLETADA", "pasos": hechos}


# Cadena de ejemplo (SUBFASE 4.7): prediccion → tarea → aprobacion → propuesta de compra.
definir("reposicion_predictiva", [
    {"accion": "crear_tarea", "params": {"modulo": "compras", "titulo": "Revisar reposicion prevista"}},
    {"accion": "solicitar_aprobacion", "params": {"entidad": "compras_pedido"},
     "requiere_aprobacion": True},
    {"accion": "crear_propuesta_compra"},
])
