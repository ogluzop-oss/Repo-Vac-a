"""
Gestos de SOMA — contrato (Fase 1: arquitectura, sin implementar).
Mapeará estados/emociones a GESTOS del personaje (p.ej. mano a la oreja al escuchar). NO implementa
animaciones (eso es del subsistema `gui/soma/animaciones`); aquí solo se define el vocabulario de
gestos que la personalidad podrá solicitar.
"""


class Gestos:
    """Contrato de gestos. Sin lógica en Fase 1."""

    def gesto_para(self, estado: str, *, emocion=None) -> str | None:
        return None
