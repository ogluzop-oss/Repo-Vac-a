"""
Mapeo de columnas del fichero a los campos canónicos (Fase 1: heurístico por sinónimos de cabecera). Devuelve
un mapeo {campo_canonico: columna_origen} que el usuario CONFIRMA (la sugerencia con IA llega en la Fase 2, y
degradará a esta heurística si no hay API). También aplica un mapeo a una fila.
"""

import logging

from src.services.importacion.modelo import CAMPOS, PRODUCTOS, _norm

logger = logging.getLogger("importacion.mapeo")


def sugerir_mapeo(columnas, entidad=PRODUCTOS) -> dict:
    """Sugiere {campo_canonico: columna_origen} emparejando cabeceras normalizadas con los sinónimos. Coincidencia
    exacta normalizada primero y, si no, por inclusión (p. ej. 'precio_venta_pvp' contiene 'pvp'). Cada columna se
    asigna a un único campo."""
    defs = CAMPOS.get(entidad, {})
    norm_cols = {col: _norm(col) for col in columnas}
    usadas = set()
    mapeo = {}
    # 1ª pasada: coincidencia exacta normalizada.
    for campo, (_req, sinonimos) in defs.items():
        sin = {_norm(s) for s in sinonimos}
        for col, ncol in norm_cols.items():
            if col in usadas:
                continue
            if ncol in sin:
                mapeo[campo] = col
                usadas.add(col)
                break
    # 2ª pasada: por inclusión (la cabecera contiene un sinónimo o viceversa).
    for campo, (_req, sinonimos) in defs.items():
        if campo in mapeo:
            continue
        sin = sorted({_norm(s) for s in sinonimos}, key=len, reverse=True)
        for col, ncol in norm_cols.items():
            if col in usadas or not ncol:
                continue
            if any(s and (s in ncol or ncol in s) for s in sin):
                mapeo[campo] = col
                usadas.add(col)
                break
    return mapeo


def campos_requeridos_faltantes(mapeo, entidad=PRODUCTOS) -> list:
    """Campos canónicos OBLIGATORIOS que el mapeo no cubre (p. ej. 'codigo')."""
    defs = CAMPOS.get(entidad, {})
    return [c for c, (req, _s) in defs.items() if req and c not in mapeo]


def aplicar_mapeo(fila, mapeo) -> dict:
    """Extrae de una fila de origen los valores canónicos según el mapeo {canonico: columna_origen}."""
    return {campo: fila.get(col) for campo, col in mapeo.items()}
