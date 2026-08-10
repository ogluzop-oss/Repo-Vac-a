"""
Emociones de SOMA — contrato (Fase 1: arquitectura, sin implementar).
Modelo emocional ligero (neutro, atento, satisfecho, preocupado, alerta…) que influirá en tono,
expresiones y gestos. Se implementará en una fase posterior.
"""


class Emociones:
    """Contrato del modelo emocional. Sin lógica en Fase 1."""

    NEUTRO = "neutro"

    def estado_emocional(self, *, contexto=None) -> str:
        return self.NEUTRO
