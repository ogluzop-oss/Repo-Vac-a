"""
Expresiones de SOMA — contrato (Fase 1: arquitectura, sin implementar).
Catálogo de expresiones verbales (saludos, confirmaciones, disculpas, avisos) parametrizables por
idioma/tono. Se poblará en una fase posterior.
"""


class Expresiones:
    """Contrato de expresiones. Sin lógica en Fase 1."""

    def obtener(self, clave: str, *, idioma="es", **params) -> str:
        return ""
