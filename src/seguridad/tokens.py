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
    # A5.1: en producción NUNCA se usa el secreto de desarrollo.
    try:
        from src.seguridad.entorno import es_produccion
        if es_produccion():
            raise RuntimeError("SMART_MANAGER_JWT_SECRET es obligatorio en producción.")
    except ImportError:
        pass
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


ACCESO_MFA_PENDING_MINUTOS = 5


def emitir_access(usuario: dict, minutos: int = ACCESO_MINUTOS, *, amr=None, auth_time=None,
                  enrollment_required: bool = False) -> str:
    """Access token. `amr` (Authentication Methods References, OIDC) documenta los factores usados:
    `["pwd"]` solo credenciales; `["pwd","otp"]`/`["pwd","webauthn"]` credenciales + segundo factor.
    Añade `mfa: true` cuando hay 2º factor. `auth_time` (unix, OIDC) = instante de la autenticación
    (para la recencia de step-up en API). `enrollment_required` marca que la política obliga a activar
    MFA y el usuario aún no lo tiene (los guards sensibles lo exigen)."""
    import jwt
    ahora = _ahora()
    payload = {**_claims_base(usuario), "type": "access", "iat": ahora,
               "exp": ahora + _dt.timedelta(minutes=minutos), "jti": str(uuid.uuid4())}
    if amr:
        amr = list(amr)
        payload["amr"] = amr
        payload["mfa"] = any(f in amr for f in ("otp", "webauthn"))
    if auth_time is not None:
        payload["auth_time"] = int(auth_time)
    if enrollment_required:
        payload["enrollment_required"] = True
    return jwt.encode(payload, _secreto(), algorithm=_ALG)


def mfa_reciente(claims: dict, max_edad_seg: int = 300) -> bool:
    """True si el token refleja un MFA COMPLETADO y RECIENTE (para step-up en API). Deriva de la
    autenticación real (claim `mfa` + `auth_time`), nunca de un booleano del cliente."""
    if not claims or not claims.get("mfa"):
        return False
    at = claims.get("auth_time")
    if at is None:
        return False
    try:
        return (int(_ahora().timestamp()) - int(at)) <= int(max_edad_seg)
    except Exception:
        return False


def emitir_mfa_pending(usuario: dict, minutos: int = ACCESO_MFA_PENDING_MINUTOS) -> str:
    """Token TEMPORAL de autenticación PARCIAL (MFA_PENDING): credenciales validadas pero 2º factor
    pendiente. NO es un access token (`type='mfa_pending'`), de modo que los endpoints protegidos —que
    exigen `type='access'`— lo RECHAZAN: no permite acceso ni saltarse el MFA. TTL corto; solo sirve
    para canjear el segundo factor en `/auth/mfa`."""
    import jwt
    ahora = _ahora()
    payload = {**_claims_base(usuario), "type": "mfa_pending", "amr": ["pwd"], "mfa": False,
               "iat": ahora, "exp": ahora + _dt.timedelta(minutes=minutos), "jti": str(uuid.uuid4())}
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
