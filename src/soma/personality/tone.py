"""
Tono de SOMA — contrato (Fase 1: arquitectura, sin implementar).
Definirá registros de comunicación (cercano, formal, urgente, alentador…) según contexto y rol.
"""


class Tono:
    """Contrato de tono. Sin lógica en Fase 1."""

    def aplicar(self, texto: str, *, registro=None, contexto=None) -> str:
        return texto
