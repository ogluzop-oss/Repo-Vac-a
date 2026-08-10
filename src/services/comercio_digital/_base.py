"""
PCD · Utilidades internas COMPARTIDAS (Etapa C0 · Prioridad 4).

Fuente ÚNICA de los helpers auxiliares que estaban duplicados en varios servicios del dominio
(`_emp`, `_publicar`, `_correlation_id`, `_verificar_firma`, `_fila`). Es un refactor PURO: no cambia
contratos, ni firmas públicas, ni comportamiento observable — solo elimina la duplicación de lógica.

Sin dependencias pesadas en import-time (solo stdlib); las capacidades/servicios se importan de forma
perezosa dentro de cada función para no introducir ciclos.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("cd.base")


def emp(id_empresa=None):
    """Resuelve el tenant: id_empresa explícito → empresa activa → EMPRESA_DEFAULT_ID."""
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def correlation_id(prefijo="cd"):
    """Correlation ID por la capacidad de Observabilidad; degradable a uuid."""
    try:
        from src.platform import capabilities as cap
        obs = cap.observabilidad()
        corr = getattr(obs, "correlation", None)
        if corr is None and obs is not None:
            import importlib
            corr = importlib.import_module("src.services.observabilidad.correlation")
        if corr is not None and hasattr(corr, "nuevo"):
            return corr.nuevo(prefijo)
    except Exception:
        pass
    return f"{prefijo}-" + uuid.uuid4().hex[:12]


def publicar_evento(tipo, *, id_empresa=None, origen=None, ref_entidad=None, ref_id=None,
                    payload=None):
    """Publica un evento por el Event Bus (capacidad, degradable). Devuelve True/False."""
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is not None and hasattr(bus, "publish"):
            bus.publish(tipo, id_empresa=id_empresa, origen=origen, ref_entidad=ref_entidad,
                        ref_id=ref_id, payload=payload)
            return True
    except Exception as e:
        logger.debug("event bus no disponible (%s): %s", tipo, e)
    return False


def hmac_valido(secret, cuerpo, firma):
    """Compara una firma HMAC-SHA256. True/False, o None si no hay secreto (degradable)."""
    if not secret:
        return None
    try:
        import hashlib
        import hmac as _hmac
        cuerpo_b = cuerpo if isinstance(cuerpo, (bytes, bytearray)) else str(cuerpo).encode()
        sec_b = secret.encode() if isinstance(secret, str) else secret
        esperado = _hmac.new(sec_b, cuerpo_b, hashlib.sha256).hexdigest()
        return _hmac.compare_digest(esperado, str(firma))
    except Exception:
        return None


def verificar_firma_webhook(clave, cuerpo, firma, id_empresa=None):
    """Verifica la firma HMAC de un webhook con el secreto de la conexión (Fase B1). None si no hay
    secreto (degradable)."""
    try:
        from src.services.comercio_digital import conexiones
        cred = conexiones.credenciales(clave, id_empresa=id_empresa)
        secret = cred.get("webhook_secret") or cred.get("secret")
        return hmac_valido(secret, cuerpo, firma)
    except Exception:
        return None


def fila_a_dict(row, cols):
    """Normaliza una fila del cursor (dict o tupla) a dict con las columnas dadas."""
    if row is None:
        return None
    return row if isinstance(row, dict) else dict(zip(cols, row))


__all__ = ["emp", "correlation_id", "publicar_evento", "hmac_valido", "verificar_firma_webhook",
           "fila_a_dict"]
