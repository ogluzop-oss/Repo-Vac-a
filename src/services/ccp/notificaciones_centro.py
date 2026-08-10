"""
Corporate Notification Center (CCP Fase II · B6) — centro ÚNICO de notificaciones.

Unifica notificaciones internas/externas/alertas/recordatorios: las INTERNAS reutilizan
`services.notificaciones` (bandeja del ERP); las EXTERNAS salen por el Corporate Communication Service
(canal según Channel Policy). No crea un segundo sistema: es una fachada de encaminamiento. Multiempresa.
API-First (sin PyQt).
"""

import logging

logger = logging.getLogger("ccp.notificaciones_centro")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def notificar(titulo, mensaje="", *, id_empresa=None, destinatario=None, usuarios=None, roles=None,
              canal=None, contexto=None, prioridad="normal", tipo="aviso", usuario=None) -> dict:
    """Encamina una notificación:
      - INTERNA (si hay usuarios/roles): `services.notificaciones.emitir` (bandeja del ERP);
      - EXTERNA (si hay `destinatario` con correo): Corporate Communication Service.
    Devuelve {interna, externa} con el resultado de cada vía."""
    id_empresa = _emp(id_empresa)
    out = {"interna": None, "externa": None}
    # Interna.
    if usuarios or roles:
        try:
            from src.services import notificaciones as _noti
            out["interna"] = _noti.emitir(tipo, titulo, mensaje, prioridad=prioridad, modulo="ccp",
                                          usuarios=usuarios, roles=roles, id_empresa=id_empresa)
        except Exception as e:
            logger.debug("notificar interna: %s", e)
    # Externa (SIEMPRE por el Communication Service; nunca un segundo sistema).
    if destinatario:
        try:
            from src.services import ccp
            res = ccp.enviar_comunicacion(id_empresa=id_empresa, destinatario=destinatario,
                                          asunto=titulo, cuerpo=mensaje, canal=canal,
                                          contexto=contexto or "notificaciones", usuario=usuario,
                                          prioridad=prioridad)
            out["externa"] = res.to_dict()
        except Exception as e:
            logger.debug("notificar externa: %s", e)
    return out


def centro(id_empresa=None, usuario=None, *, limite=100) -> dict:
    """Vista agregada del centro: notificaciones internas pendientes + últimas comunicaciones
    externas (unificado, no separado por sistema)."""
    id_empresa = _emp(id_empresa)
    internas, externas = [], []
    try:
        from src.services import notificaciones as _noti
        internas = _noti.pendientes_usuario(usuario, id_empresa=id_empresa, limite=limite) if usuario \
            else _noti.listar(id_empresa=id_empresa, limite=limite)
    except Exception as e:
        logger.debug("centro internas: %s", e)
    try:
        from src.services.ccp import servicio as _svc
        externas = _svc.historial_comunicaciones(id_empresa, limite=limite)
    except Exception as e:
        logger.debug("centro externas: %s", e)
    return {"internas": internas, "externas": externas}
