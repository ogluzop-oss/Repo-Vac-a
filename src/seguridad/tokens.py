"""
Tokens JWT / refresh (C1.4 — DISEÑO preparado para la futura API REST/SaaS/móvil).

Define la emisión/verificación de tokens y la estructura de *claims* multi-tenant
(`sub`, `empresa`, `tienda`, `rol`). NO expone endpoints (eso es A1): solo deja la
base lista y testeable. Los refresh tokens se persisten *hasheados* en la tabla
`sesiones` (ver src/db/sesiones.py) para poder revocarlos.

Firma HS256 con una clave derivada de la clave maestra (rota con ella); puede
fijarse explícitamente con `SMART_MANAGER_JWT_SECRET`. En multi-servicio se podrá
pasar a RS256 sin cambiar la interfaz.
"""

import datetime as _dt
import hashlib
import logging
import os
import uuid

logger = logging.getLogger("seguridad.tokens")

ACCESO_MINUTOS = 15
REFRESH_DIAS = 30
_ALG = "HS256"


def _secreto() -> str:
    s = os.getenv("SMART_MANAGER_JWT_SECRET")
    if s:
        return s
    try:
        from src.utils import cripto
        clave = cripto._cargar_o_crear_clave()
        if clave:
            return hashlib.sha256(b"jwt:" + clave).hexdigest()
    except Exception as e:
        logger.debug("No se pudo derivar el secreto JWT de la clave maestra: %s", e)
    logger.warning("Usando secreto JWT de desarrollo; define SMART_MANAGER_JWT_SECRET.")
    return "dev-insecure-jwt-secret-change-me"


def _ahora():
    return _dt.datetime.now(_dt.timezone.utc)


def _claims_base(usuario: dict) -> dict:
    return {
        "sub": str(usuario.get("id")),
        "empresa": usuario.get("id_empresa"),
        "tienda": usuario.get("tienda_id"),
        "rol": usuario.get("perfil"),
        "nombre": usuario.get("nombre"),
    }


def emitir_access(usuario: dict, minutos: int = ACCESO_MINUTOS) -> str:
    import jwt
    ahora = _ahora()
    payload = {**_claims_base(usuario), "type": "access", "iat": ahora,
               "exp": ahora + _dt.timedelta(minutes=minutos), "jti": str(uuid.uuid4())}
    return jwt.encode(payload, _secreto(), algorithm=_ALG)


def emitir_refresh(usuario: dict, dias: int = REFRESH_DIAS) -> tuple[str, str, _dt.datetime]:
    """Devuelve (token, jti, expira_utc). El jti permite revocarlo en `sesiones`."""
    import jwt
    ahora = _ahora()
    jti = str(uuid.uuid4())
    expira = ahora + _dt.timedelta(days=dias)
    payload = {"sub": str(usuario.get("id")), "empresa": usuario.get("id_empresa"),
               "type": "refresh", "iat": ahora, "exp": expira, "jti": jti}
    return jwt.encode(payload, _secreto(), algorithm=_ALG), jti, expira


def verificar(token: str, tipo: str | None = None) -> dict | None:
    """Verifica firma y expiración. Si `tipo` se indica, exige type==tipo."""
    import jwt
    try:
        datos = jwt.decode(token, _secreto(), algorithms=[_ALG])
    except Exception as e:
        logger.debug("Token inválido: %s", e)
        return None
    if tipo and datos.get("type") != tipo:
        return None
    return datos


def hash_refresh(token: str) -> str:
    """Hash para almacenar el refresh token en reposo (no se guarda en claro)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
