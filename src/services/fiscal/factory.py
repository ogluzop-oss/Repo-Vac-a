"""Selección de proveedor/firmante/emisor según la config de la empresa (C3.1/C3.2)."""

import logging

from src.services.fiscal.base import Emisor, Firmante
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


def firmante_para(config: dict) -> Firmante:
    """Firmante para una config. En C3.2 no-op (no firma); el certificado local
    cifrado/HSM llega en C3.5 como adaptadores enchufables sin tocar el núcleo."""
    return Firmante()


def emisor_para(config: dict) -> Emisor:
    """Emisor para una config. Verifactu devuelve su adaptador AEAT con TRANSPORTE
    mTLS real (C3.5.2) inyectado cuando la empresa tiene un certificado ACTIVO
    vigente (custodia C3.5.1). Sin certificado, `disponible()=False` → el worker
    deja el registro en espera. Otros regímenes/sin configurar: no-op."""
    if (config or {}).get("proveedor") == "verifactu":
        try:
            from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
            transporte = _transporte_mtls(config)
            return EmisorVerifactu(transporte=transporte, config=config)
        except Exception as e:
            logger.error("emisor_para(verifactu): %s", e)
    return Emisor()


def _transporte_mtls(config: dict):
    """Transporte mTLS a partir del certificado activo de la empresa, o None."""
    try:
        from src.services.fiscal import certificados as C
        from src.services.fiscal.emisores.tls import transporte_mtls
        prov = C.proveedor_claves((config or {}).get("id_empresa"))
        return transporte_mtls(prov) if prov is not None else None
    except Exception as e:
        logger.debug("transporte mTLS no disponible: %s", e)
        return None
