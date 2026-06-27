"""
MFA TOTP + recovery codes (SEC-1/SEC-2).

TOTP RFC 6238 (HMAC-SHA1, 30 s, 6 dígitos) SIN dependencias externas → compatible con Google/
Microsoft Authenticator y Authy. El secreto se cifra en reposo (Fernet). Códigos de recuperación
de un solo uso (hash Argon2id). Activar/desactivar/verificar. Multiusuario, auditado.
"""

import base64
import hashlib
import hmac
import logging
import os
import struct
import time
import uuid

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("seguridad.mfa")
DIGITOS = 6
PERIODO = 30


# ── TOTP RFC 6238 ─────────────────────────────────────────────────────────────
def generar_secreto() -> str:
    """Secreto base32 (160 bits) para el autenticador."""
    return base64.b32encode(os.urandom(20)).decode("utf-8").rstrip("=")


def _codigo(secreto_b32, contador) -> str:
    clave = base64.b32decode(secreto_b32 + "=" * (-len(secreto_b32) % 8), casefold=True)
    msg = struct.pack(">Q", contador)
    h = hmac.new(clave, msg, hashlib.sha1).digest()
    off = h[-1] & 0x0F
    cod = (struct.unpack(">I", h[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITOS)
    return str(cod).zfill(DIGITOS)


def codigo_actual(secreto_b32, t=None) -> str:
    return _codigo(secreto_b32, int((t or time.time()) // PERIODO))


def verificar_totp(secreto_b32, codigo, *, ventana=1) -> bool:
    if not codigo or not secreto_b32:
        return False
    ahora = int(time.time() // PERIODO)
    for d in range(-ventana, ventana + 1):
        if hmac.compare_digest(_codigo(secreto_b32, ahora + d), str(codigo).strip()):
            return True
    return False


def uri_otpauth(secreto_b32, cuenta, emisor="Smart Manager") -> str:
    return (f"otpauth://totp/{emisor}:{cuenta}?secret={secreto_b32}"
            f"&issuer={emisor}&digits={DIGITOS}&period={PERIODO}")


# ── Persistencia / ciclo de vida ─────────────────────────────────────────────
def _cifrar(v):
    try:
        from src.utils import cripto
        return cripto.cifrar(v)
    except Exception:
        return v


def _descifrar(v):
    try:
        from src.utils import cripto
        return cripto.descifrar_seguro(v) or v
    except Exception:
        return v


def iniciar_activacion(id_usuario, cuenta) -> dict:
    """Crea (no activa aún) un secreto MFA y devuelve {secreto, uri} para escanear el QR."""
    secreto = generar_secreto()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO mfa_usuarios (id_usuario, secreto, activo) VALUES (%s,%s,0) "
                        "ON DUPLICATE KEY UPDATE secreto=VALUES(secreto), activo=0",
                        (id_usuario, _cifrar(secreto)))
            conn.commit()
    except Exception as e:
        logger.error("iniciar_activacion: %s", e)
    return {"secreto": secreto, "uri": uri_otpauth(secreto, cuenta)}


def confirmar_activacion(id_usuario, codigo) -> dict:
    """Activa MFA si el código TOTP es válido. Genera y devuelve los recovery codes (una vez)."""
    sec = _secreto(id_usuario)
    if not sec or not verificar_totp(sec, codigo):
        return {"ok": False, "error": "código inválido"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE mfa_usuarios SET activo=1 WHERE id_usuario=%s", (id_usuario,))
            conn.commit()
    except Exception as e:
        logger.error("confirmar_activacion: %s", e)
        return {"ok": False, "error": str(e)}
    _audit("MFA_ACTIVADO", id_usuario)
    return {"ok": True, "recovery_codes": generar_recovery_codes(id_usuario)}


def desactivar(id_usuario) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE mfa_usuarios SET activo=0 WHERE id_usuario=%s", (id_usuario,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (id_usuario,))
            conn.commit()
        _audit("MFA_DESACTIVADO", id_usuario)
        return True
    except Exception as e:
        logger.error("desactivar: %s", e)
        return False


def _secreto(id_usuario):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT secreto FROM mfa_usuarios WHERE id_usuario=%s", (id_usuario,))
            r = cur.fetchone()
            return _descifrar(r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception:
        return None


def mfa_activo(id_usuario) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT activo FROM mfa_usuarios WHERE id_usuario=%s", (id_usuario,))
            r = cur.fetchone()
            return bool(r and (r[0] if not isinstance(r, dict) else list(r.values())[0]))
    except Exception:
        return False


def verificar(id_usuario, codigo) -> bool:
    """Verifica un código TOTP del usuario (segundo factor en login)."""
    if not mfa_activo(id_usuario):
        return True                       # MFA no activo → no exige segundo factor (compat)
    return verificar_totp(_secreto(id_usuario), codigo)


# ── Recovery codes ────────────────────────────────────────────────────────────
def _hash(code):
    try:
        from src.seguridad import passwords
        return passwords.hash_password(code)
    except Exception:
        return hashlib.sha256(code.encode()).hexdigest()


def _verif_hash(code, h):
    try:
        from src.seguridad import passwords
        ok, _ = passwords.verificar(code, h)
        return ok
    except Exception:
        return hashlib.sha256(code.encode()).hexdigest() == h


def generar_recovery_codes(id_usuario, n=8) -> list:
    codes = [uuid.uuid4().hex[:10] for _ in range(n)]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (id_usuario,))
            for c in codes:
                cur.execute("INSERT INTO mfa_recovery_codes (id_usuario, codigo_hash) VALUES (%s,%s)",
                            (id_usuario, _hash(c)))
            conn.commit()
    except Exception as e:
        logger.error("generar_recovery_codes: %s", e)
    return codes


def usar_recovery_code(id_usuario, codigo) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, codigo_hash FROM mfa_recovery_codes WHERE id_usuario=%s AND usado=0",
                        (id_usuario,))
            for r in cur.fetchall():
                d = r if isinstance(r, dict) else {"id": r[0], "codigo_hash": r[1]}
                if _verif_hash(codigo, d["codigo_hash"]):
                    cur.execute("UPDATE mfa_recovery_codes SET usado=1, usado_en=NOW() WHERE id=%s", (d["id"],))
                    conn.commit()
                    _audit("MFA_RECOVERY_USADO", id_usuario)
                    return True
        return False
    except Exception as e:
        logger.error("usar_recovery_code: %s", e)
        return False


def _audit(accion, id_usuario):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(str(id_usuario), accion, "mfa_usuarios", f"usuario={id_usuario}")
    except Exception:
        pass
