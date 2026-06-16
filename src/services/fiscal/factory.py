"""Selección del proveedor fiscal según la config de la empresa (C3.1)."""

import logging

from src.services.fiscal.registry import clase_de, proveedor_para_territorio

logger = logging.getLogger("fiscal.factory")


def proveedor_para(config: dict):
    """Proveedor para una config dada: por nombre y, si no, por territorio; cae a
    'simulado'."""
    nombre = (config or {}).get("proveedor")
    clase = clase_de(nombre) if nombre else None
    if clase is None:
        clase = proveedor_para_territorio((config or {}).get("territorio", "comun"))
    if clase is None:
        clase = clase_de("simulado")
    return clase(config) if clase else None


def proveedor_fiscal_actual():
    """Proveedor fiscal de la empresa activa (según `fiscal_config`)."""
    try:
        from src.db import fiscal as fiscal_db
        return proveedor_para(fiscal_db.obtener_config())
    except Exception as e:
        logger.error("proveedor_fiscal_actual: %s", e)
        return proveedor_para({})
