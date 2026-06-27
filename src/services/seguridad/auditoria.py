"""
Auditoría de eventos de seguridad (FASE 10).

Envoltorio fino sobre `conexion.log_auditoria` para registrar de forma homogénea los eventos
de seguridad (login/logout, contraseña, alta/baja de usuario, cambios de rol/permiso/grupo,
denegaciones, eventos ACL). Best-effort: nunca rompe la operación que lo invoca.
"""

import logging

logger = logging.getLogger("seguridad.auditoria")

EVENTOS = (
    "LOGIN", "LOGIN_FALLIDO", "LOGOUT", "CAMBIO_PASSWORD",
    "ALTA_USUARIO", "BAJA_USUARIO", "CAMBIO_ROL", "CAMBIO_PERMISO", "CAMBIO_GRUPO",
    "PERMISO_DENEGADO", "ACL_CAMBIO",
)


def registrar(accion, *, usuario=None, detalles=None, ip=None, tabla="seguridad"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(str(usuario) if usuario is not None else "sistema", accion, tabla,
                      detalles, ip)
    except Exception as e:
        logger.debug("auditoria.registrar(%s): %s", accion, e)
