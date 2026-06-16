"""
Hashing de contraseñas — Argon2id con migración transparente desde SHA-256.

- Las contraseñas NUEVAS se almacenan con Argon2id (`$argon2id$…`, sal embebida).
- Las antiguas (SHA-256 = 64 hex) se siguen validando y, en el primer login
  correcto, se **rehashean** automáticamente a Argon2id (ver `verificar`).
- Si por algún motivo Argon2 no está disponible, se degrada a SHA-256 para no
  bloquear el acceso (situación no esperada: argon2-cffi está en requirements).

`verificar(pw, hash)` devuelve `(ok, hash_nuevo|None)`: si `hash_nuevo` no es None,
conviene persistirlo (rehash). Mantiene compatibilidad con los usuarios actuales.
"""

import hashlib
import hmac
import logging
import re

logger = logging.getLogger("seguridad.passwords")

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
    # Parámetros equilibrados (OWASP): ~64 MB, 3 iteraciones, 2 hilos.
    _ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
    _ARGON2 = True
except Exception as e:  # pragma: no cover
    _ph = None
    _ARGON2 = False
    logger.warning("Argon2 no disponible (%s); se usará SHA-256 como respaldo.", e)

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def es_hash_legado(h: str) -> bool:
    """True si el hash es del esquema antiguo SHA-256 (64 hexadecimales)."""
    return bool(h and _HEX64.match(h.strip()))


def _sha256(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def hash_password(pw: str) -> str:
    """Hash de una contraseña en texto plano (Argon2id; SHA-256 si no hay Argon2)."""
    if _ph is not None:
        return _ph.hash(pw)
    return _sha256(pw)


def necesita_actualizar(h: str) -> bool:
    """True si el hash debería re-generarse (legado o parámetros Argon2 obsoletos)."""
    if es_hash_legado(h):
        return _ARGON2
    if _ph is not None:
        try:
            return _ph.check_needs_rehash(h)
        except Exception:
            return False
    return False


def verificar(pw: str, hash_almacenado: str) -> tuple[bool, str | None]:
    """Verifica `pw` contra `hash_almacenado`.

    Devuelve `(ok, hash_nuevo|None)`. `hash_nuevo` se rellena cuando conviene
    rehashear (hash legado o parámetros Argon2 desactualizados) para que el
    llamante lo persista."""
    if not hash_almacenado:
        return (False, None)
    h = hash_almacenado.strip()

    if es_hash_legado(h):
        ok = hmac.compare_digest(_sha256(pw), h.lower())
        nuevo = hash_password(pw) if (ok and _ARGON2) else None
        return (ok, nuevo)

    if _ph is not None:
        try:
            _ph.verify(h, pw)
        except (VerifyMismatchError, InvalidHashError):
            return (False, None)
        except Exception as e:  # pragma: no cover
            logger.debug("Error verificando Argon2: %s", e)
            return (False, None)
        nuevo = hash_password(pw) if _ph.check_needs_rehash(h) else None
        return (True, nuevo)

    # Sin Argon2 y hash no legado: nada que comparar de forma fiable.
    return (False, None)
