"""
Fachada de fichajes RRHH (F3.0.1).

Reexporta las funciones de fichaje desde `src.db.usuario` SIN mover ni duplicar
lógica. Punto de entrada estable para el futuro módulo RRHH; cuando la lógica se
traslade aquí, los consumidores ya importarán desde esta ruta.
"""

from src.db.usuario import (  # noqa: F401  (reexport intencionado)
    listar_fichajes,
    obtener_fichaje_abierto,
    registrar_entrada,
    registrar_salida,
    validar_pin_fichaje,
)

__all__ = [
    "registrar_entrada",
    "registrar_salida",
    "listar_fichajes",
    "obtener_fichaje_abierto",
    "validar_pin_fichaje",
]
