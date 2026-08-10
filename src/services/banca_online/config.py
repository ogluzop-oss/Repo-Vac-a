"""
Configuración de la conexión bancaria por cuenta. La credencial se guarda CIFRADA (Secret Manager, patrón
MFA/ESL) — jamás en claro. Construye el `BancaGateway` a partir de la config.
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.banca_online.gateway import BancaGateway

logger = logging.getLogger("banca.config")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _descifrar(cif):
    if not cif:
        return None
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.descifrar(cif)
    except Exception as e:
        logger.error("descifrar credencial banca: %s", e)
        return None


def guardar_conexion(id_cuenta, *, proveedor="simulado", endpoint=None, account_id=None, credencial=None,
                     modo_simulado=True, id_empresa=None):
    """Crea/actualiza la conexión de una cuenta. `credencial` se cifra; si es None se conserva la existente."""
    eid = _emp(id_empresa)
    cif = None
    if credencial:
        try:
            from src.services.seguridad import secret_manager
            cif = secret_manager.cifrar(credencial)
        except Exception as e:
            logger.error("cifrar credencial banca: %s", e)
            cif = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO banca_conexiones (id_empresa,id_cuenta,proveedor,endpoint,account_id,"
                "credencial_cifrada,modo_simulado) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE proveedor=VALUES(proveedor),endpoint=VALUES(endpoint),"
                "account_id=VALUES(account_id),"
                "credencial_cifrada=COALESCE(VALUES(credencial_cifrada),credencial_cifrada),"
                "modo_simulado=VALUES(modo_simulado)",
                (eid, id_cuenta, proveedor, endpoint, account_id, cif, 1 if modo_simulado else 0))
            return True
    except Exception as e:
        logger.error("guardar_conexion: %s", e)
        return False


def obtener_config(id_cuenta, id_empresa=None, incluir_credencial=False):
    """Config de la cuenta SIN la credencial cifrada. Con `incluir_credencial`, añade `_credencial` descifrada."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM banca_conexiones WHERE id_empresa=%s AND id_cuenta=%s",
                        (_emp(id_empresa), id_cuenta))
            filas = _filas_a_dicts(cur, cur.fetchall())
            if not filas:
                return None
            cfg = filas[0]
            cred = cfg.pop("credencial_cifrada", None)
            cfg["tiene_credencial"] = bool(cred)
            if incluir_credencial:
                cfg["_credencial"] = _descifrar(cred)
            return cfg
    except Exception as e:
        logger.error("obtener_config: %s", e)
        return None


def gateway(id_cuenta, id_empresa=None, transport=None):
    cfg = obtener_config(id_cuenta, id_empresa, incluir_credencial=True)
    if not cfg:
        return BancaGateway(modo_simulado=True, transport=transport)
    return BancaGateway(proveedor=cfg.get("proveedor") or "simulado", endpoint=cfg.get("endpoint"),
                        account_id=cfg.get("account_id"), credencial=cfg.get("_credencial"),
                        modo_simulado=bool(cfg.get("modo_simulado", 1)), transport=transport)


def marcar_sync(id_cuenta, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE banca_conexiones SET ultima_sync=%s WHERE id_empresa=%s AND id_cuenta=%s",
                        (_dt.datetime.now(), _emp(id_empresa), id_cuenta))
    except Exception as e:
        logger.debug("marcar_sync: %s", e)
