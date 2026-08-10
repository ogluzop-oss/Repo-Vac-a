"""
Subsistema de PERSONALIDAD de SOMA — ARQUITECTURA (Fase 1). Solo se deja preparada la estructura;
la personalidad NO se implementa todavía (fases posteriores). Define los contratos de tono,
expresiones, gestos y emociones que modularán las respuestas y el comportamiento del personaje.
"""

from src.soma.personality import (emotions, expressions, gestures,  # noqa: F401
                                   personality, tone)

__all__ = ["personality", "tone", "expressions", "gestures", "emotions"]
