"""
ESL — Etiquetas electrónicas de precio dinámico (Fase 1: núcleo, push MANUAL, degradable).

Capas:
  · `gateway.ESLGateway` — puente degradable con el proveedor (simulado / REST real).
  · `config`   — configuración por empresa+tienda (credencial cifrada) + fábrica del gateway.
  · `registro` — mapeo etiqueta ↔ artículo (vincular/desvincular/listar).
  · `sync`     — cálculo de pendientes + push manual + localizar.

Toda la lógica vive aquí (services/); la GUI (fase posterior) solo orquesta. RBAC `esl.*`.
"""

from src.services.esl import config, registro, sync
from src.services.esl.gateway import ESLGateway

__all__ = ["config", "registro", "sync", "ESLGateway"]
