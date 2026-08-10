"""
WebAuthn / Passkeys (Gobernanza MFA · Fase 5) — capa RELYING PARTY (servidor). SEGUNDO método MFA,
ADICIONAL a TOTP (que sigue como fallback). Reutiliza la librería estándar `webauthn` (py_webauthn);
NO implementa criptografía WebAuthn a mano. DEGRADABLE: si la librería no está disponible, `disponible()`
es False y las operaciones devuelven `webauthn_unavailable` (como el resto de features degradables).

La ceremonia real (`navigator.credentials.create/get`) ocurre en el NAVEGADOR del cliente contra los
endpoints REST; aquí solo se generan las opciones (con `challenge`) y se VERIFICAN las respuestas.
Se guardan SOLO datos PÚBLICOS de la credencial (credential_id, clave pública COSE, sign_count):
NUNCA claves privadas ni secretos del autenticador. Multiempresa, auditado.
"""

import base64
import hashlib
import hmac
import logging
import os
import time

logger = logging.getLogger("seguridad.mfa_webauthn")

# Perfiles de MAYOR riesgo para los que se RECOMIENDA passkey (además de TOTP).
ROLES_RECOMENDADO = ("SUPERADMIN", "ADMINISTRADOR", "GERENTE")


def _rp_id():
    return os.getenv("SMART_MANAGER_WEBAUTHN_RP_ID", "localhost").strip() or "localhost"


def _rp_name():
    return os.getenv("SMART_MANAGER_WEBAUTHN_RP_NAME", "Smart Manager").strip() or "Smart Manager"


def _origin():
    return os.getenv("SMART_MANAGER_WEBAUTHN_ORIGIN", f"https://{_rp_id()}").strip()


def disponible() -> bool:
    try:
        import webauthn  # noqa: F401
        return True
    except Exception:
        return False


def webauthn_recomendado(perfil) -> bool:
    return str(perfil or "").upper() in ROLES_RECOMENDADO


# ── Firma del challenge (flujo REST sin estado): el reto se devuelve firmado (HMAC) y con TTL. ──
def _secret():
    try:
        from src.seguridad import tokens
        return tokens._secreto().encode()
    except Exception:
        return b"dev-webauthn"


def _firmar_reto(challenge: bytes, ttl=300) -> str:
    b64 = base64.urlsafe_b64encode(challenge).decode()
    exp = str(int(time.time()) + ttl)
    payload = f"{b64}.{exp}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verificar_reto(token: str):
    try:
        b64, exp, sig = token.rsplit(".", 2)
        good = hmac.new(_secret(), f"{b64}.{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig) or int(exp) < time.time():
            return None
        return base64.urlsafe_b64decode(b64.encode())
    except Exception:
        return None


# ── Persistencia (solo datos públicos) ────────────────────────────────────────
def _b64u(b):
    from webauthn.helpers import bytes_to_base64url
    return bytes_to_base64url(b)


def _de_b64u(s):
    from webauthn.helpers import base64url_to_bytes
    return base64url_to_bytes(s)


def listar(id_usuario) -> list:
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, nombre, credential_id, transports, creado, ultima_uso "
                        "FROM mfa_webauthn_credenciales WHERE id_usuario=%s AND revocado=0 "
                        "ORDER BY creado DESC", (str(id_usuario),))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar webauthn: %s", e)
        return []


def revocar(id_credencial, *, actor=None) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_usuario, id_empresa FROM mfa_webauthn_credenciales WHERE id=%s",
                        (id_credencial,))
            r = cur.fetchone()
            cur.execute("UPDATE mfa_webauthn_credenciales SET revocado=1 WHERE id=%s", (id_credencial,))
            c.commit()
        try:
            from src.services.seguridad import mfa_eventos
            uid = (r[0] if not isinstance(r, dict) else r.get("id_usuario")) if r else None
            mfa_eventos.emitir("MFA_DISABLED", id_usuario=uid, actor=actor, detalle="webauthn revocada")
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        logger.error("revocar webauthn: %s", e)
        return {"ok": False, "error": str(e)}


def _credenciales_usuario(id_usuario):
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    with obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT credential_id, public_key, sign_count, transports FROM "
                    "mfa_webauthn_credenciales WHERE id_usuario=%s AND revocado=0", (str(id_usuario),))
        return _filas_a_dicts(cur, cur.fetchall())


# ── Ceremonias (relying party) ────────────────────────────────────────────────
def iniciar_registro(usuario, *, rp_id=None, origin=None) -> dict:
    """Genera las opciones de registro (para `navigator.credentials.create`). Devuelve el JSON de
    opciones y un `reto` firmado que el cliente debe reenviar en `confirmar_registro`."""
    if not disponible():
        return {"ok": False, "error": "webauthn_unavailable"}
    try:
        import webauthn
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
        uid = str((usuario or {}).get("id"))
        excl = []
        for c in _credenciales_usuario(uid):
            try:
                excl.append(PublicKeyCredentialDescriptor(id=_de_b64u(c["credential_id"])))
            except Exception:
                pass
        opts = webauthn.generate_registration_options(
            rp_id=rp_id or _rp_id(), rp_name=_rp_name(),
            user_id=uid.encode(), user_name=(usuario or {}).get("nombre") or uid,
            exclude_credentials=excl)
        return {"ok": True, "options": webauthn.options_to_json(opts),
                "reto": _firmar_reto(opts.challenge)}
    except Exception as e:
        logger.error("iniciar_registro webauthn: %s", e)
        return {"ok": False, "error": str(e)}


def confirmar_registro(usuario, reto, respuesta, *, rp_id=None, origin=None, nombre=None) -> dict:
    """Verifica la respuesta del autenticador y GUARDA la credencial (solo datos públicos)."""
    if not disponible():
        return {"ok": False, "error": "webauthn_unavailable"}
    challenge = _verificar_reto(reto)
    if challenge is None:
        return {"ok": False, "error": "reto_invalido"}
    try:
        import webauthn
        v = webauthn.verify_registration_response(
            credential=respuesta, expected_challenge=challenge,
            expected_rp_id=rp_id or _rp_id(), expected_origin=origin or _origin())
    except Exception as e:
        logger.debug("verify_registration_response: %s", e)
        return {"ok": False, "error": "verificacion_fallida"}
    try:
        from src.db.conexion import obtener_conexion
        uid = str((usuario or {}).get("id"))
        emp = (usuario or {}).get("id_empresa")
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO mfa_webauthn_credenciales (id_usuario, id_empresa, credential_id, "
                "public_key, sign_count, nombre, rp_id) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE public_key=VALUES(public_key), sign_count=VALUES(sign_count), "
                "revocado=0",
                (uid, emp, _b64u(v.credential_id), _b64u(v.credential_public_key),
                 int(getattr(v, "sign_count", 0) or 0), nombre or "Passkey", rp_id or _rp_id()))
            c.commit()
        try:
            from src.services.seguridad import mfa_eventos
            mfa_eventos.emitir("MFA_ENROLLED", id_usuario=uid, id_empresa=emp, detalle="webauthn")
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        logger.error("guardar credencial webauthn: %s", e)
        return {"ok": False, "error": str(e)}


def iniciar_login(usuario) -> dict:
    if not disponible():
        return {"ok": False, "error": "webauthn_unavailable"}
    try:
        import webauthn
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
        allow = []
        for c in _credenciales_usuario(str((usuario or {}).get("id"))):
            try:
                allow.append(PublicKeyCredentialDescriptor(id=_de_b64u(c["credential_id"])))
            except Exception:
                pass
        if not allow:
            return {"ok": False, "error": "sin_passkeys"}
        opts = webauthn.generate_authentication_options(rp_id=_rp_id(), allow_credentials=allow)
        return {"ok": True, "options": webauthn.options_to_json(opts),
                "reto": _firmar_reto(opts.challenge)}
    except Exception as e:
        logger.error("iniciar_login webauthn: %s", e)
        return {"ok": False, "error": str(e)}


def confirmar_login(usuario, reto, respuesta, *, rp_id=None, origin=None) -> dict:
    if not disponible():
        return {"ok": False, "error": "webauthn_unavailable"}
    challenge = _verificar_reto(reto)
    if challenge is None:
        return {"ok": False, "error": "reto_invalido"}
    try:
        import json as _json

        import webauthn
        cred = respuesta if isinstance(respuesta, dict) else _json.loads(respuesta)
        cid = cred.get("id") or cred.get("rawId")
        fila = None
        for c in _credenciales_usuario(str((usuario or {}).get("id"))):
            if c["credential_id"] == cid:
                fila = c
                break
        if not fila:
            return {"ok": False, "error": "credencial_desconocida"}
        v = webauthn.verify_authentication_response(
            credential=respuesta, expected_challenge=challenge,
            expected_rp_id=rp_id or _rp_id(), expected_origin=origin or _origin(),
            credential_public_key=_de_b64u(fila["public_key"]),
            credential_current_sign_count=int(fila.get("sign_count") or 0))
    except Exception as e:
        logger.debug("verify_authentication_response: %s", e)
        return {"ok": False, "error": "verificacion_fallida"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE mfa_webauthn_credenciales SET sign_count=%s, ultima_uso=NOW() "
                        "WHERE credential_id=%s", (int(getattr(v, "new_sign_count", 0) or 0), cid))
            c.commit()
    except Exception as e:
        logger.debug("update sign_count: %s", e)
    return {"ok": True}
