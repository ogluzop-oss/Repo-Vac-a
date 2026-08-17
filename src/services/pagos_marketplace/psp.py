"""
Resolutor del adaptador de PSP con capacidades de MARKETPLACE (F1 + credenciales de PLATAFORMA).

En un marketplace, los fondos se mueven en la cuenta Stripe Connect de la PLATAFORMA (el operador de Smart
Manager), NO en la de cada empresa compradora. Por eso las credenciales de Connect son ÚNICAS de plataforma:

Prioridad de la config de plataforma (`config_plataforma`):
  1. Variables de entorno del operador (STRIPE_CONNECT_SECRET_KEY / STRIPE_CONNECT_WEBHOOK_SECRET / …),
  2. fila reservada en `pasarela_config` (tenant `__mkt_platform__`, secretos cifrados Fernet, reutilizada),
  3. si no hay nada → adaptador SIMULADO (degradable, sin custodia real).

El adaptador resultante sabe hacer cuentas conectadas + escrow. Es independiente del proveedor que cada
empresa tenga fijado para su TPV/checkout.
"""

import logging
import os

logger = logging.getLogger("pagos_marketplace.psp")

# Tenant reservado donde se guardan las credenciales Connect de la PLATAFORMA (no es una empresa real).
TENANT_PLATAFORMA = "__mkt_platform__"


def config_plataforma() -> dict:
    """Credenciales/ajustes de Connect de la plataforma (env → pasarela_config reservada → {})."""
    env_key = os.environ.get("STRIPE_CONNECT_SECRET_KEY") or os.environ.get("STRIPE_PLATFORM_KEY")
    if env_key:
        whsec = os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET", "")
        try:
            comision = float(os.environ.get("MARKETPLACE_FEE_PCT", "0") or 0)
        except ValueError:
            comision = 0.0
        return {"proveedor": "stripe_connect", "api_key": env_key, "webhook_secret": whsec,
                "webhook_secret_connect": whsec, "modo": os.environ.get("STRIPE_MODE", "test"),
                "pais": os.environ.get("STRIPE_COUNTRY", "ES"), "comision_pct": comision,
                "origen": "env"}
    try:
        from src.db import pagos as pagos_db
        row = pagos_db.obtener_config(TENANT_PLATAFORMA) or {}
        # La fila de plataforma dedica `webhook_secret` al webhook de Connect.
        row["webhook_secret_connect"] = row.get("webhook_secret") or ""
        row["origen"] = "pasarela_config"
        return row
    except Exception as e:
        logger.debug("config_plataforma: %s", e)
        return {}


def guardar_config_plataforma(*, api_key=None, webhook_secret=None, modo=None) -> bool:
    """Guarda (cifrado) las credenciales Connect de la plataforma en la fila reservada. Admin/superadmin."""
    try:
        from src.db import pagos as pagos_db
        return pagos_db.guardar_config(proveedor="stripe_connect", api_key=api_key,
                                       webhook_secret=webhook_secret, modo=modo,
                                       id_empresa=TENANT_PLATAFORMA)
    except Exception as e:
        logger.error("guardar_config_plataforma: %s", e)
        return False


def adaptador(id_empresa=None, config=None):
    """Adaptador de marketplace. Usa las credenciales de PLATAFORMA salvo que se pase `config` (testeable).
    `id_empresa` se conserva por compatibilidad/traza (las credenciales NO son por empresa)."""
    from src.services.tpv.pagos.registry import clase_de
    cfg = config if config is not None else config_plataforma()

    cls = clase_de("stripe_connect")
    if cls is not None:
        try:
            ad = cls(cfg)
            if ad.configurado():
                return ad
        except Exception as e:
            logger.debug("adaptador stripe_connect: %s", e)

    sim = clase_de("simulado_mkt")
    if sim is not None:
        return sim(cfg)
    from src.services.tpv.pagos.base_marketplace import PasarelaMarketplace
    return PasarelaMarketplace(cfg)
