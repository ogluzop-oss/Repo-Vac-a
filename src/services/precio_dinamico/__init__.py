"""
Precio dinámico — reglas de ajuste automático de precio (horario / stock / caducidad).

La ESL es la capa de VISUALIZACIÓN: este motor recalcula `articulos.precio` (a partir de `precio_base`,
no destructivo) y ESL detecta los cambios como etiquetas PENDIENTES. `aplicar()` es el callable que puede
ejecutarse a mano (GUI) o de forma periódica (scheduler). RBAC `precio_dinamico.*`.
"""

from src.services.precio_dinamico import motor, reglas

__all__ = ["motor", "reglas"]
