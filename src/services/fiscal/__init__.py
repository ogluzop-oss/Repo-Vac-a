"""
Núcleo fiscal (C3) — proveedores por territorio, enchufables.

C3.1 deja cerradas las interfaces (`RegistroFiscal`/`Firmante`/`Emisor`/
`ProveedorFiscal`), el registro/descubrimiento de proveedores y un proveedor
`simulado` funcional (encadenado hash real, sin lógica legal). Verifactu/Facturae/
TicketBAI se añaden como módulos sin tocar el núcleo.
"""

MODULOS = [
    "simulado",
]

from src.services.fiscal.base import (Emisor, Firmante, ProveedorFiscal,
                                      RegistroFiscal)
from src.services.fiscal.factory import proveedor_fiscal_actual, proveedor_para

__all__ = ["RegistroFiscal", "Firmante", "Emisor", "ProveedorFiscal",
           "proveedor_fiscal_actual", "proveedor_para"]
