"""
Mobile · Push (Fase V · Bloque 1). Notificaciones push del dispositivo. REUTILIZA el sistema de
notificaciones/CCP existente (nunca un canal paralelo): registrar el token del dispositivo y enviar
avisos delegando en el Centro de Notificaciones. Degradable si el backend de push no está activo.
"""

from __future__ import annotations

_DISPOSITIVOS = {}     # id_usuario -> [token_push, ...] (en la app nativa lo gestiona el backend)


def registrar_dispositivo(id_usuario, token_push, *, plataforma="android") -> bool:
    if not id_usuario or not token_push:
        return False
    _DISPOSITIVOS.setdefault(str(id_usuario), [])
    if token_push not in _DISPOSITIVOS[str(id_usuario)]:
        _DISPOSITIVOS[str(id_usuario)].append(token_push)
    return True


def dispositivos(id_usuario) -> list:
    return list(_DISPOSITIVOS.get(str(id_usuario), []))


def enviar(id_usuario, titulo, cuerpo, *, id_empresa=None, datos=None) -> dict:
    """Envía un push reutilizando el Centro de Notificaciones (o CCP). Degradable."""
    entregado = False
    try:
        from src.services import notificaciones as _notif
        if hasattr(_notif, "crear"):
            _notif.crear(titulo=titulo, mensaje=cuerpo, id_usuario=id_usuario,
                         id_empresa=id_empresa, canal="push")
            entregado = True
    except Exception:
        pass
    if not entregado:
        try:
            from src.services import ccp
            ccp.registrar_evento("push", id_empresa=id_empresa, destinatario=str(id_usuario))
            entregado = True
        except Exception:
            pass
    return {"entregado": entregado, "dispositivos": len(dispositivos(id_usuario)),
            "titulo": titulo}


__all__ = ["registrar_dispositivo", "dispositivos", "enviar"]
