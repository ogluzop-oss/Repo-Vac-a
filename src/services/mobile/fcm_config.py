"""
Configuración GLOBAL del sistema de push FCM — fila única (`id=1`). El proyecto Firebase es propiedad
del VENDEDOR de Smart Manager, no de cada empresa cliente: se reutiliza para todas las empresas, sin
gate por plan SaaS (disponible para Basic, Pro y Plus por igual).

El JSON del *service account* se guarda CIFRADO (Secret Manager, mismo patrón que
`services/esl/config.py`) — jamás en claro.
"""

import json
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.mobile.fcm import FCMGateway

logger = logging.getLogger("mobile.fcm_config")

_ID_GLOBAL = 1


def _descifrar(cif):
    if not cif:
        return None
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.descifrar(cif)
    except Exception as e:
        logger.error("descifrar service account FCM: %s", e)
        return None


def guardar_config(project_id=None, service_account_json=None, modo_simulado=True):
    """Crea/actualiza la configuración FCM global (una única fila). `service_account_json` (dict o str
    JSON) se cifra; si es None se conserva la existente (no se borra al reeditar el resto de campos)."""
    cif = None
    if service_account_json:
        try:
            texto = (service_account_json if isinstance(service_account_json, str)
                     else json.dumps(service_account_json))
            from src.services.seguridad import secret_manager
            cif = secret_manager.cifrar(texto)
        except Exception as ex:
            logger.error("cifrar service account FCM: %s", ex)
            cif = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fcm_config (id,project_id,service_account_cifrado,modo_simulado) "
                "VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE project_id=VALUES(project_id),"
                "service_account_cifrado=COALESCE(VALUES(service_account_cifrado),"
                "service_account_cifrado),modo_simulado=VALUES(modo_simulado)",
                (_ID_GLOBAL, project_id, cif, 1 if modo_simulado else 0))
            return True
    except Exception as ex:
        logger.error("guardar_config: %s", ex)
        return False


def obtener_config(incluir_credencial=False):
    """Configuración FCM global como dict SIN la credencial cifrada. Si `incluir_credencial`, añade el
    service account descifrado (dict) en `_service_account` (uso interno del gateway)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fcm_config WHERE id=%s", (_ID_GLOBAL,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            if not filas:
                return None
            cfg = filas[0]
            cred = cfg.pop("service_account_cifrado", None)
            cfg["tiene_credencial"] = bool(cred)
            if incluir_credencial:
                texto = _descifrar(cred)
                try:
                    cfg["_service_account"] = json.loads(texto) if texto else None
                except Exception:
                    cfg["_service_account"] = None
            return cfg
    except Exception as ex:
        logger.error("obtener_config: %s", ex)
        return None


def gateway():
    """Construye el FCMGateway GLOBAL (mismo proyecto para todas las empresas). Sin config → SIMULADO."""
    cfg = obtener_config(incluir_credencial=True)
    if not cfg:
        return FCMGateway(modo_simulado=True)
    return FCMGateway(
        project_id=cfg.get("project_id"),
        service_account_json=cfg.get("_service_account"),
        modo_simulado=bool(cfg.get("modo_simulado", 1)))
