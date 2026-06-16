"""
Gestión de entorno y secretos críticos (A5.1).

En PRODUCCIÓN (`SMART_MANAGER_ENV=prod`) la aplicación/servidor **no debe arrancar**
sin los secretos obligatorios (secreto JWT y clave maestra de cifrado por entorno).
En desarrollo, solo se avisa para no entorpecer pruebas.

El backend (API) llama a `validar_arranque_seguro()` al crear la app.
"""

import logging
import os

logger = logging.getLogger("seguridad.entorno")

_PROD = ("prod", "produccion", "producción", "production")


def es_produccion() -> bool:
    return os.getenv("SMART_MANAGER_ENV", "dev").strip().lower() in _PROD


def secretos_faltantes() -> list:
    """Secretos críticos que faltan para un arranque seguro en producción.

    En producción se EXIGE que el secreto JWT y la clave maestra vengan por
    ENTORNO (no del fichero de desarrollo auto-generado)."""
    faltan = []
    if not os.getenv("SMART_MANAGER_JWT_SECRET"):
        faltan.append("SMART_MANAGER_JWT_SECRET")
    if not (os.getenv("SMART_MANAGER_SECRET_KEY") or os.getenv("SMART_MANAGER_SECRET_KEYS")):
        faltan.append("clave maestra (SMART_MANAGER_SECRET_KEY / SMART_MANAGER_SECRET_KEYS)")
    return faltan


def validar_arranque_seguro() -> bool:
    """Fail-fast en producción si faltan secretos; aviso en desarrollo.
    Devuelve True si todo está presente."""
    faltan = secretos_faltantes()
    if faltan and es_produccion():
        raise RuntimeError(
            "Arranque abortado (producción): faltan secretos críticos por entorno: "
            + ", ".join(faltan))
    if faltan:
        logger.warning("Secretos no definidos (modo desarrollo, se continúa): %s",
                       ", ".join(faltan))
    return not faltan
