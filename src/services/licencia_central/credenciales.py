"""
Credenciales M2M de esta instalación (client_id/client_secret emitidos por el servidor central al
activarse — Fase 2). El `client_secret` se cifra en reposo con `utils.cripto` (misma utilidad ya
usada para el IBAN de la suscripción, `services/saas/suscripciones.py`); se guarda en el mismo
JSON per-install que `identidad.py` (`config_instalacion.json`) — vive fuera de cualquier base de
datos, porque debe sobrevivir incluso a una reinstalación/reset de la BD local.
"""

import logging

from src.services.licencia_central import identidad as _id

logger = logging.getLogger("licencia_central.credenciales")


def guardar(client_id: str, client_secret: str) -> bool:
    """Cifra y persiste las credenciales M2M de esta instalación."""
    try:
        from src.utils import cripto
        cifrado = cripto.cifrar(client_secret)
        if not cifrado:
            logger.error("No se pudo cifrar el client_secret (cifrado no disponible).")
            return False
        datos = _id._leer()
        datos["activado"] = True
        datos["client_id"] = client_id
        datos["client_secret_cifrado"] = cifrado
        return _id._escribir(datos)
    except Exception as e:
        logger.error("guardar credenciales: %s", e)
        return False


def obtener() -> tuple[str, str] | None:
    """Devuelve (client_id, client_secret) descifrado, o None si la instalación no está
    activada (o el descifrado falla, p. ej. clave maestra distinta tras restaurar un backup en
    otra máquina — en ese caso hay que reactivar)."""
    datos = _id._leer()
    client_id = datos.get("client_id")
    cifrado = datos.get("client_secret_cifrado")
    if not client_id or not cifrado:
        return None
    try:
        from src.utils import cripto
        secreto = cripto.descifrar(cifrado)
        if not secreto:
            return None
        return client_id, secreto
    except Exception as e:
        logger.error("obtener credenciales: %s", e)
        return None
