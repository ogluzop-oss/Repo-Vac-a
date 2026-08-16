"""
Resolutor del adaptador de PSP con capacidades de MARKETPLACE (F1).

Reutiliza las MISMAS credenciales del PSP (`pasarela_config`, cifradas) que el checkout, pero garantiza que
el adaptador devuelto sabe hacer cuentas conectadas + escrow. Prioridad:
  1. Stripe Connect (`stripe_connect`) si hay `api_key` configurada,
  2. en su defecto, el fallback SIMULADO (`simulado_mkt`) — degradable, para desarrollo/pruebas.

Así el resto de la capa (cuentas, escrow) no depende de qué proveedor esté fijado para el TPV.
"""

import logging

logger = logging.getLogger("pagos_marketplace.psp")


def adaptador(id_empresa=None, config=None):
    """Adaptador de marketplace para la empresa. Si se pasa `config`, no consulta la BD (testeable)."""
    from src.services.tpv.pagos.registry import clase_de
    if config is None:
        try:
            from src.db import pagos as pagos_db
            config = pagos_db.obtener_config(id_empresa)
        except Exception as e:
            logger.debug("adaptador: sin config (%s)", e)
            config = {}

    cls = clase_de("stripe_connect")
    if cls is not None:
        try:
            ad = cls(config)
            if ad.configurado():
                return ad
        except Exception as e:
            logger.debug("adaptador stripe_connect: %s", e)

    sim = clase_de("simulado_mkt")
    if sim is not None:
        return sim(config)
    # Último recurso: interfaz base (no soporta nada, pero no rompe).
    from src.services.tpv.pagos.base_marketplace import PasarelaMarketplace
    return PasarelaMarketplace(config)
