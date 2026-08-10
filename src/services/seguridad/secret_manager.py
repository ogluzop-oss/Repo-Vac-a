"""
Vault abstraction (SEC-7) + cifrado avanzado (SEC-8).

Capa única de gestión de secretos con backends intercambiables:
  • 'fernet' (por defecto): cifra/descifra con src.utils.cripto (rotación de claves soportada).
  • 'vault'  (futuro): punto de extensión; no obliga a instalar nada.
  • 'aws_secrets_manager' (Fase 10, PREPARADO): lee secretos de AWS Secrets Manager vía boto3 perezoso.
API: cifrar/descifrar/rotar. Mantiene compatibilidad con el cifrado actual. INTERFAZ ÚNICA (no se duplica el
sistema de secretos): sólo cambia el backend por configuración `SM_SECRET_BACKEND`.
"""

import logging
import os
import time

logger = logging.getLogger("seguridad.secret_manager")

_AWS_CACHE = {}          # clave -> (valor, expira_en)
_AWS_TTL = 300           # cache controlado (5 min); rotación/expiración vía Secrets Manager


def _backend():
    return os.getenv("SM_SECRET_BACKEND", "fernet").lower()


def _secret_id(clave) -> str:
    """Nombre real del secreto en AWS Secrets Manager. Se antepone `SM_SECRET_PREFIX` (por ENTORNO) para que
    dev/staging/prod convivan en la misma cuenta sin colisión y coincidan con la IaC (module `secrets`, que
    nombra los secretos `${project}-${environment}/<CLAVE>`). Sin prefijo, se usa la clave desnuda."""
    pref = os.getenv("SM_SECRET_PREFIX", "")
    return f"{pref}{clave}" if pref else clave


def _aws_get(clave):
    """Lee un secreto de AWS Secrets Manager (boto3 perezoso, cache controlado). None si no disponible.
    NO hace fallback silencioso a un secreto inseguro: devuelve None y el llamador decide."""
    ahora = time.time()
    sid = _secret_id(clave)
    hit = _AWS_CACHE.get(sid)
    if hit and hit[1] > ahora:
        return hit[0]
    try:
        import boto3
    except Exception:
        logger.debug("boto3 no instalado: aws_secrets_manager PREPARADO, no operativo")
        return None
    try:
        cli = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
        r = cli.get_secret_value(SecretId=sid)
        val = r.get("SecretString")
        _AWS_CACHE[sid] = (val, ahora + _AWS_TTL)
        return val
    except Exception as e:
        logger.error("aws secreto '%s': %s", sid, e)
        return None


def cifrar(valor) -> str | None:
    if valor is None:
        return None
    if _backend() == "vault":
        # Punto de extensión para HashiCorp Vault / KMS (no implementado: degrada a fernet).
        logger.debug("backend vault no configurado; uso fernet")
    from src.utils import cripto
    return cripto.cifrar(valor)


def descifrar(token) -> str | None:
    if token is None:
        return None
    from src.utils import cripto
    return cripto.descifrar_seguro(token)


def rotar(token) -> str | None:
    """Re-cifra un secreto con la clave actual (rotación). Best-effort."""
    try:
        from src.utils import cripto
        if hasattr(cripto, "rotar"):
            return cripto.rotar(token)
        claro = cripto.descifrar_seguro(token)
        return cripto.cifrar(claro) if claro else token
    except Exception as e:
        logger.error("rotar: %s", e)
        return token


def obtener_secreto(clave, default=None):
    """Recupera un secreto con NOMBRE desde el backend de secretos configurado.

    backend 'vault' (futuro) → punto de extensión HashiCorp Vault / cloud KMS (no implementado).
    Fallback universal: variable de entorno homónima. Devuelve `default` si no existe.
    Permite a los módulos resolver credenciales sin fichero en disco."""
    if not clave:
        return default
    b = _backend()
    if b == "aws_secrets_manager":
        val = _aws_get(clave)
        if val is not None:
            return val
        # Sin fallback silencioso a inseguro en producción: sólo cae a entorno fuera de prod.
        if os.getenv("ENVIRONMENT", "dev").lower() == "production":
            logger.warning("secreto '%s' no resuelto por AWS en producción (sin fallback inseguro)", clave)
            return default
        logger.debug("aws no resolvió '%s'; fuera de producción se usa entorno", clave)
    elif b == "vault":
        # Punto de extensión: aquí se consultaría Vault/KMS. Degrada a entorno.
        logger.debug("backend vault no configurado; resuelvo '%s' por entorno", clave)
    return os.getenv(clave, default)


def disponible_vault() -> bool:
    return False


def disponible_aws() -> bool:
    """True si el backend AWS puede usarse (boto3 presente). No garantiza credenciales/secreto real."""
    try:
        import boto3  # noqa: F401
        return True
    except Exception:
        return False


def backend_activo() -> str:
    return _backend()
