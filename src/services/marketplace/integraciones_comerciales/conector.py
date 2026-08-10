"""
Integraciones Comerciales · Conector PREPARADO (Fase WEB-03). Implementación única y genérica que cubre TODOS
los contratos para CUALQUIER plataforma del catálogo, elevando `NotImplementedError` (no duplica una clase por
plataforma → evita copiar código). Cuando se implemente cada plataforma, se especializará este conector o se
registrará uno propio. NO realiza ninguna conexión real.
"""

from src.services.marketplace.integraciones_comerciales import contratos


class ConectorPreparado(contratos.ConectorMarketplace, contratos.ConectorProductos,
                        contratos.ConectorPedidos, contratos.ConectorClientes,
                        contratos.ConectorInventario, contratos.ConectorPrecios):
    """Conector genérico para una plataforma concreta. `disponible()` = False (sin integración real);
    el resto hereda los `NotImplementedError` de los contratos."""

    def __init__(self, plataforma):
        self.plataforma = plataforma

    def disponible(self) -> bool:
        return False

    def descriptor(self) -> dict:
        return {"plataforma": self.plataforma, "disponible": self.disponible(),
                "contratos": [c.__name__ for c in contratos.CONTRATOS], "estado": "PREPARADO"}


def conector(plataforma) -> ConectorPreparado:
    """Devuelve el conector PREPARADO de una plataforma (validando que exista en el catálogo)."""
    from src.services.comercio_digital.integraciones_comerciales import catalogo
    if catalogo.obtener(plataforma) is None:
        raise ValueError(f"plataforma no reconocida: {plataforma}")
    return ConectorPreparado(plataforma)
