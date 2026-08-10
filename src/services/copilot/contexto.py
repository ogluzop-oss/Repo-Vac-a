"""
Contexto empresarial del Copiloto (Paquete Enterprise 5, SUBFASE 5.3). Resuelve automaticamente
empresa/tienda/usuario/rol/idioma/periodo desde la sesion y el contexto activo. No pide al usuario
lo que el sistema ya sabe.
"""

import logging

logger = logging.getLogger("copilot.contexto")


def _sesion():
    try:
        from src.db.usuario import sesion_global
        return getattr(sesion_global, "usuario_actual", None) or {}
    except Exception:
        return {}


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _tienda():
    try:
        from src.db.conexion import tienda_actual_id_int
        return int(tienda_actual_id_int() or 0)
    except Exception:
        return 0


def _idioma():
    try:
        from src.utils import i18n
        return getattr(i18n, "idioma_actual", lambda: "es")() if hasattr(i18n, "idioma_actual") else "es"
    except Exception:
        return "es"


def resolver(usuario=None, id_empresa=None) -> dict:
    u = usuario or _sesion()
    if isinstance(u, dict):
        rol = u.get("perfil")
        uid = u.get("nombre") or u.get("usuario") or (str(u.get("id")) if u.get("id") else None)
        tienda = u.get("id_tienda")
    else:
        rol, uid, tienda = None, (str(u) if u else None), None
    return {
        "id_empresa": _empresa(id_empresa),
        "id_tienda": int(tienda) if tienda is not None else _tienda(),
        "usuario": uid,
        "rol": (rol or "OPERARIO").upper(),
        "idioma": _idioma(),
        "periodo": "dia",
    }
