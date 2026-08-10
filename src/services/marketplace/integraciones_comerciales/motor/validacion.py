"""
Motor · SISTEMA DE VALIDACIÓN (Fase WEB-13). Define las comprobaciones que un validador REAL ejecutará en el
futuro (URL/credenciales/versión/API/permisos/estado/SSL). En esta fase NO valida nada realmente: devuelve un
informe con cada comprobación en estado PREPARADO. Sin llamadas externas.
"""

# Comprobaciones canónicas (orden lógico).
COMPROBACIONES = ("url", "credenciales", "version", "api", "permisos", "estado", "ssl")


class Validador:
    """Validador PREPARADO. Cada comprobación es un hook que un adaptador real implementará. Aquí ninguna
    comprobación se ejecuta: se informa `preparado`."""

    def __init__(self, plataforma=None):
        self.plataforma = (plataforma or "").lower() or None

    def comprobaciones(self) -> tuple:
        return COMPROBACIONES

    def validar(self, config=None) -> dict:
        """Informe de validación PREPARADO (no ejecuta ninguna comprobación real)."""
        return {"plataforma": self.plataforma, "estado": "PREPARADO",
                "comprobaciones": {c: "preparado" for c in COMPROBACIONES}}
