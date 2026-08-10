"""
Adaptador Hostinger · SECRETOS (Fase WEB-14). Resuelve las credenciales de Hostinger EXCLUSIVAMENTE mediante
el `SecretManager` existente (`services.seguridad.secret_manager`). Nunca en variables globales, ficheros JSON
ni texto plano en el código. El modelo de integración guarda solo la REFERENCIA (nombre del secreto).
"""

CLAVE_DEFECTO = "HOSTINGER_API_TOKEN"


def token(credenciales_ref=None):
    """Token/clave de API de Hostinger resuelto por el SecretManager (backend fernet/AWS/vault/entorno).
    Devuelve None si no hay credenciales configuradas → el adaptador NO estará disponible (honesto)."""
    ref = credenciales_ref or CLAVE_DEFECTO
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.obtener_secreto(ref)
    except Exception:
        return None


def cifrar(valor):
    """Cifra un valor sensible (p. ej. token OAuth obtenido en runtime) con el SecretManager. Nunca se
    persiste el valor en claro."""
    try:
        from src.services.seguridad import secret_manager
        return secret_manager.cifrar(valor)
    except Exception:
        return None
