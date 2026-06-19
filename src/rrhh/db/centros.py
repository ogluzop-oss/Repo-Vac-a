"""
Fachada de centros de trabajo RRHH (F3.0.1).

Reexporta `src.db.centros` sin mover ni duplicar lógica.
"""

from src.db.centros import (  # noqa: F401  (reexport intencionado)
    actualizar_centro,
    baja_centro,
    centro_principal,
    crear_centro,
    listar_centros,
    marcar_principal,
    obtener_centro,
)

__all__ = [
    "listar_centros",
    "obtener_centro",
    "centro_principal",
    "crear_centro",
    "actualizar_centro",
    "marcar_principal",
    "baja_centro",
]
