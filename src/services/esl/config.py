"""
Configuración del sistema ESL por empresa+tienda. La credencial del proveedor se guarda CIFRADA
(Secret Manager, patrón MFA) — jamás en claro. Construye el `ESLGateway` a partir de la config.
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.esl.gateway import ESLGateway

logger = logging.getLogger("esl.config")


def _ctx(id_empresa=None, id_tienda=None):
    """Normaliza (empresa, tienda) a cadena — evita NULLs en la clave única (empresa, tienda)."""
    if id_empresa is None:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    if id_tienda is None:
        try:
            from src.db.empresa import tienda_actual_id
            id_tienda = tienda_actual_id()
        except Exception:
            id_tienda = None
    return (id_empresa or ""), (id_tienda or "")


def _descifrar(cif):
    if not cif:
        return None
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.descifrar(cif)
    except Exception as e:
        logger.error("descifrar credencial ESL: %s", e)
        return None


def guardar_config(proveedor="simulado", endpoint=None, store_id=None, credencial=None,
                   modo_simulado=True, id_empresa=None, id_tienda=None):
    """Crea/actualiza la config ESL de (empresa, tienda). `credencial` se cifra; si es None se conserva
    la existente (no se borra al reeditar el resto de campos)."""
    e, t = _ctx(id_empresa, id_tienda)
    cif = None
    if credencial:
        try:
            from src.services.seguridad import secret_manager
            cif = secret_manager.cifrar(credencial)
        except Exception as ex:
            logger.error("cifrar credencial ESL: %s", ex)
            cif = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO esl_config (id_empresa,id_tienda,proveedor,endpoint,store_id,"
                "credencial_cifrada,modo_simulado) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE proveedor=VALUES(proveedor),endpoint=VALUES(endpoint),"
                "store_id=VALUES(store_id),"
                "credencial_cifrada=COALESCE(VALUES(credencial_cifrada),credencial_cifrada),"
                "modo_simulado=VALUES(modo_simulado)",
                (e, t, proveedor, endpoint, store_id, cif, 1 if modo_simulado else 0))
            return True
    except Exception as ex:
        logger.error("guardar_config: %s", ex)
        return False


def obtener_config(id_empresa=None, id_tienda=None, incluir_credencial=False):
    """Config de (empresa, tienda) como dict SIN la credencial cifrada. Si `incluir_credencial`, añade la
    credencial descifrada en `_credencial` (uso interno del gateway; nunca se expone en la GUI)."""
    e, t = _ctx(id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM esl_config WHERE id_empresa=%s AND id_tienda=%s", (e, t))
            filas = _filas_a_dicts(cur, cur.fetchall())
            if not filas:
                return None
            cfg = filas[0]
            cred = cfg.pop("credencial_cifrada", None)
            cfg["tiene_credencial"] = bool(cred)
            if incluir_credencial:
                cfg["_credencial"] = _descifrar(cred)
            return cfg
    except Exception as ex:
        logger.error("obtener_config: %s", ex)
        return None


def gateway(id_empresa=None, id_tienda=None):
    """Construye el ESLGateway de (empresa, tienda). Sin config → gateway SIMULADO."""
    cfg = obtener_config(id_empresa, id_tienda, incluir_credencial=True)
    if not cfg:
        return ESLGateway(modo_simulado=True)
    return ESLGateway(
        proveedor=cfg.get("proveedor") or "simulado",
        endpoint=cfg.get("endpoint"),
        store_id=cfg.get("store_id"),
        credencial=cfg.get("_credencial"),
        modo_simulado=bool(cfg.get("modo_simulado", 1)))
