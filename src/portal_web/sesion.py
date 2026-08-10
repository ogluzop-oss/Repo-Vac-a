"""
Portal Web (Back Office) · Sesión/Autenticación (Fase WEB-04). REUTILIZA el sistema de autenticación existente
(JWT + MFA + WebAuthn); NO crea uno propio. En la API el contexto autenticado lo resuelve
`api.security.requiere_auth` (tenant SIEMPRE del token). Aquí sólo se describen los métodos disponibles
(preparado); ninguna implementación paralela.
"""


def metodos_autenticacion() -> dict:
    """Métodos de auth soportados por el portal, reutilizando la infraestructura existente."""
    def _disp(mod):
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    return {
        "login": True,
        "logout": True,
        "jwt": _disp("src.services.seguridad.tokens") or _disp("jwt"),
        "mfa": _disp("src.services.seguridad.mfa"),
        "webauthn": _disp("src.services.seguridad.mfa_webauthn"),
        "fuente_tenant": "token",   # id_empresa/id_tienda salen del token, nunca del dominio
    }
