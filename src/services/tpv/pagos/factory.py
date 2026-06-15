"""Selección de la pasarela de pago según la config de la empresa.

No conoce las pasarelas concretas: las resuelve desde el registro
(``registry``), que las descubre automáticamente. Añadir una pasarela nueva no
requiere tocar este fichero.
"""

import logging

from src.services.tpv.pagos.registry import (clase_de, pasarelas_registradas,
                                             proveedor_por_defecto)

logger = logging.getLogger("pagos.factory")


def pasarela_para(config: dict):
    """Pasarela para una config dada. Si el proveedor no se reconoce, cae a la
    recomendada y, en último término, a 'simulado'."""
    nombre = (config or {}).get("proveedor") or proveedor_por_defecto()
    clase = clase_de(nombre) or clase_de(proveedor_por_defecto()) or clase_de("simulado")
    if clase is None:                       # registro vacío (no debería ocurrir)
        from src.services.tpv.pagos.base import PasarelaPago
        return PasarelaPago(config)
    return clase(config)


def pasarela_actual():
    """Pasarela del proveedor configurado para la empresa activa."""
    try:
        from src.db import pagos as pagos_db
        return pasarela_para(pagos_db.obtener_config())
    except Exception as e:
        logger.error("pasarela_actual: %s", e)
        return pasarela_para({})


# Reexport para comodidad de la UI.
__all__ = ["pasarela_para", "pasarela_actual", "pasarelas_registradas",
           "proveedor_por_defecto"]
