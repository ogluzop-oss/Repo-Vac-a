"""
Reset MFA administrativo (Gobernanza MFA · Fase 3). Permite a un administrador (permiso
`mfa.admin.reset`) resetear el segundo factor de otro usuario que ha perdido su dispositivo, dejándolo
sin MFA para que vuelva a enrolarse. Reutiliza el motor existente (`mfa.desactivar`: activo=0 + borra
los recovery codes) y la auditoría (`mfa_eventos`). No crea tabla ni motor nuevos.

Seguridad: la reautenticación reciente y el step-up del administrador se exigen en la UI (diálogo);
aquí se hace además la comprobación RBAC de defensa en profundidad. NUNCA se registran secretos.
"""

import logging

logger = logging.getLogger("seguridad.mfa_admin")


def _nombre_actor(usuario_actor):
    if isinstance(usuario_actor, dict):
        return usuario_actor.get("nombre") or usuario_actor.get("usuario")
    return usuario_actor


def reset_mfa(id_objetivo, *, usuario_actor=None, id_empresa=None, motivo=None) -> dict:
    """Resetea el MFA del usuario `id_objetivo`. Requiere `mfa.admin.reset` del actor (se comprueba si
    se pasa `usuario_actor`). Emite `MFA_RESET` con actor/usuario/empresa/motivo (sin secretos).
    Tras el reset, el usuario deberá volver a configurar su MFA."""
    if not id_objetivo:
        return {"ok": False, "error": "sin_objetivo"}
    if usuario_actor is not None:
        try:
            from src.services import autorizacion
            if not autorizacion.puede(usuario_actor, "mfa.admin.reset", id_empresa=id_empresa):
                return {"ok": False, "error": "forbidden", "permiso": "mfa.admin.reset"}
        except Exception as e:
            logger.debug("RBAC reset_mfa: %s", e)
    try:
        from src.services.seguridad import mfa, mfa_eventos
        ok = mfa.desactivar(id_objetivo)   # activo=0 + borra recovery codes → obliga a re-enrolar
        if ok:
            mfa_eventos.emitir("MFA_RESET", id_usuario=id_objetivo, id_empresa=id_empresa,
                               actor=_nombre_actor(usuario_actor),
                               detalle=f"motivo={(motivo or '-')}")
        return {"ok": bool(ok)}
    except Exception as e:
        logger.error("reset_mfa: %s", e)
        return {"ok": False, "error": str(e)}
