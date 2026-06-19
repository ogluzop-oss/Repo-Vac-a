"""
Fachada de representantes legales RRHH (F3.0.1).

Reexporta `src.db.representantes` sin mover ni duplicar lógica.
"""

from src.db.representantes import (  # noqa: F401  (reexport intencionado)
    actualizar_representante,
    baja_representante,
    crear_representante,
    listar_representantes,
    marcar_principal,
    obtener_representante,
    representante_principal,
)

__all__ = [
    "listar_representantes",
    "obtener_representante",
    "representante_principal",
    "crear_representante",
    "actualizar_representante",
    "marcar_principal",
    "baja_representante",
]
