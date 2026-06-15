"""Selección de la pasarela de pago según la config de la empresa."""

import logging

from src.services.tpv.pagos.paypal import PasarelaPayPal
from src.services.tpv.pagos.redsys import PasarelaRedsys
from src.services.tpv.pagos.simulado import PasarelaSimulada
from src.services.tpv.pagos.stripe import PasarelaStripe

logger = logging.getLogger("pagos.factory")

_PASARELAS = {
    "simulado": PasarelaSimulada,
    "stripe": PasarelaStripe,
    "paypal": PasarelaPayPal,
    "redsys": PasarelaRedsys,
}


def pasarela_para(config: dict):
    """Pasarela para una config dada (cae a 'simulado' si el proveedor no se reconoce)."""
    clase = _PASARELAS.get((config or {}).get("proveedor", "simulado"), PasarelaSimulada)
    return clase(config)


def pasarela_actual():
    """Pasarela del proveedor configurado para la empresa activa."""
    try:
        from src.db import pagos as pagos_db
        return pasarela_para(pagos_db.obtener_config())
    except Exception as e:
        logger.error("pasarela_actual: %s", e)
        return PasarelaSimulada({})
