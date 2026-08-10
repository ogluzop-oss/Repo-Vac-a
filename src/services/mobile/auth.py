"""
Mobile · Auth (Fase V · Bloque 1). Ciclo de vida de autenticación móvil REUTILIZANDO la seguridad
existente: JWT (`src.seguridad.tokens`), refresh token, MFA/TOTP (`src.services.seguridad.mfa`),
más los factores locales del dispositivo (PIN/biometría) y revocación remota. No crea un segundo
sistema de auth: envuelve el oficial. Sin BD directa.
"""

from __future__ import annotations

FACTORES_LOCALES = ("pin", "biometria")


def emitir_tokens(usuario: dict) -> dict:
    """Emite access + refresh para un usuario ya autenticado (tenant en los claims)."""
    from src.seguridad import tokens
    access = tokens.emitir_access(usuario)
    refresh, _jti, _exp = tokens.emitir_refresh(usuario)
    return {"access": access, "refresh": refresh, "tipo": "Bearer"}


def verificar(token: str, tipo: str = "access") -> dict | None:
    from src.seguridad import tokens
    return tokens.verificar(token, tipo)


def refrescar(refresh_token: str) -> dict | None:
    """Renueva el access token a partir de un refresh válido."""
    from src.seguridad import tokens
    claims = tokens.verificar(refresh_token, "refresh")
    if not claims:
        return None
    usuario = {"id": claims.get("sub"), "id_empresa": claims.get("empresa"),
               "perfil": claims.get("rol"), "nombre": claims.get("nombre")}
    return emitir_tokens(usuario)


def mfa_requerido(id_usuario) -> bool:
    try:
        from src.services.seguridad import mfa
        return bool(mfa.mfa_activo(id_usuario))
    except Exception:
        return False


def verificar_mfa(id_usuario, codigo) -> bool:
    try:
        from src.services.seguridad import mfa
        return bool(mfa.verificar(id_usuario, codigo) or mfa.usar_recovery_code(id_usuario, codigo))
    except Exception:
        return False


def revocar_remoto(id_usuario) -> bool:
    """Revocación remota de sesiones del dispositivo (reutiliza la revocación de tokens si existe)."""
    try:
        from src.seguridad import tokens
        if hasattr(tokens, "revocar_usuario"):
            tokens.revocar_usuario(id_usuario)
            return True
    except Exception:
        pass
    return False


def descriptor() -> dict:
    return {"metodos": ["oauth", "jwt", "refresh_token", "mfa"] + list(FACTORES_LOCALES),
            "revocacion_remota": True}


__all__ = ["FACTORES_LOCALES", "emitir_tokens", "verificar", "refrescar", "mfa_requerido",
           "verificar_mfa", "revocar_remoto", "descriptor"]
