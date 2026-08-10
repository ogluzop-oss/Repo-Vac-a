"""
Eventos de auditoría MFA (Gobernanza MFA · Fase 0). NO es un motor de eventos nuevo: es una fachada
fina que canaliza los eventos MFA por la infraestructura EXISTENTE — `log_auditoria` (persistente) y
`registrar_evento` (observabilidad). Taxonomía canónica para todas las fases MFA.

REGLA DE SEGURIDAD: NUNCA se registran secretos. Esta fachada no acepta el secreto TOTP, ni recovery
codes, ni tokens, ni contraseñas; además sanea el `detalle` eliminando claves sensibles por si acaso.
"""

import logging
import re

logger = logging.getLogger("seguridad.mfa_eventos")

# Taxonomía canónica de eventos MFA (Fase 0 + cierre: STEP_UP_*).
EVENTOS = (
    "MFA_ENROLLMENT_STARTED", "MFA_ENROLLED", "MFA_CHALLENGE", "MFA_SUCCESS", "MFA_FAILURE",
    "MFA_DISABLED", "MFA_RESET", "MFA_RECOVERY_USED", "TRUSTED_DEVICE_ADDED",
    "TRUSTED_DEVICE_REVOKED", "MFA_POLICY_CHANGED",
    "STEP_UP_REQUIRED", "STEP_UP_SUCCESS", "STEP_UP_FAILURE",
)

# Patrones cuyo VALOR jamás debe aparecer en un log de auditoría MFA.
_SENSIBLE = re.compile(
    r"(secreto|secret|totp|recovery|c[oó]digo|code|token|password|contrase|hash)\s*[=:]\s*\S+",
    re.IGNORECASE)


def _sanea(detalle) -> str:
    txt = str(detalle or "")
    return _SENSIBLE.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***", txt)[:255]


def emitir(evento, *, id_usuario=None, id_empresa=None, actor=None, detalle="", nivel="info") -> None:
    """Registra un evento MFA en auditoría + observabilidad. `evento` debe pertenecer a EVENTOS.
    No pasar NUNCA secretos por `detalle` (se sanea de todos modos)."""
    if evento not in EVENTOS:
        logger.debug("evento MFA desconocido: %s", evento)
    det = _sanea(detalle)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("seguridad_mfa", evento, "mfa",
                      f"usuario={id_usuario} empresa={id_empresa} actor={actor} {det}"[:255])
    except Exception as e:
        logger.debug("log_auditoria MFA: %s", e)
    try:
        from src.utils.observabilidad import registrar_evento
        registrar_evento("mfa", evento, nivel=nivel,
                         usuario=id_usuario, empresa=id_empresa, actor=actor)
    except Exception as e:
        logger.debug("registrar_evento MFA: %s", e)
