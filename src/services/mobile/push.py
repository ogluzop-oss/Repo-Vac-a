"""
Mobile · Push (Fase V · Bloque 1, + Push FCM real). Notificaciones push del dispositivo. REUTILIZA el
sistema de notificaciones/CCP existente para el HISTORIAL (nunca un canal paralelo) y AÑADE entrega real
por Firebase Cloud Messaging — un ÚNICO proyecto GLOBAL (`services/mobile/fcm_config`, propiedad del
vendedor de Smart Manager, no de cada empresa cliente) — a los tokens de dispositivo, ahora persistidos
en la tabla `dispositivos_push` (antes vivían solo en memoria, perdidos en cada reinicio del backend —
inaceptable para un guardia que depende del aviso de antihurto). Degradable: sin config FCM, el envío
queda en modo simulado (ver `FCMGateway`) sin romper el registro en el Centro de Notificaciones.

Este módulo es infraestructura genérica de envío, sin gate por plan SaaS: el push antihurto (ver
`services/rfid/antihurto.py`) está disponible para todas las empresas clientes, sea cual sea su plan.
"""

from __future__ import annotations

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("mobile.push")


def registrar_dispositivo(id_usuario, token_push, *, plataforma="android", id_empresa=None) -> bool:
    if not id_usuario or not token_push:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dispositivos_push (id_empresa,id_usuario,token,plataforma,activo) "
                "VALUES (%s,%s,%s,%s,1) "
                "ON DUPLICATE KEY UPDATE activo=1, plataforma=VALUES(plataforma), "
                "actualizado=CURRENT_TIMESTAMP",
                (id_empresa, str(id_usuario), token_push, plataforma))
            return True
    except Exception as ex:
        logger.error("registrar_dispositivo: %s", ex)
        return False


def dispositivos(id_usuario, id_empresa=None) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if id_empresa is None:
                cur.execute(
                    "SELECT token FROM dispositivos_push WHERE id_usuario=%s AND activo=1",
                    (str(id_usuario),))
            else:
                cur.execute(
                    "SELECT token FROM dispositivos_push WHERE id_usuario=%s AND id_empresa=%s "
                    "AND activo=1",
                    (str(id_usuario), id_empresa))
            return [f[0] for f in cur.fetchall()]
    except Exception as ex:
        logger.error("dispositivos: %s", ex)
        return []


def enviar(id_usuario, titulo, cuerpo, *, id_empresa=None, datos=None) -> dict:
    """Envía un push: registra en el Centro de Notificaciones (o CCP, fuente de verdad del historial) y
    AÑADE el intento de entrega real por FCM a cada dispositivo registrado del usuario. Degradable."""
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

    tokens = dispositivos(id_usuario, id_empresa)
    intentados = len(tokens)
    ok = 0
    if tokens:
        try:
            from src.services.mobile import fcm_config
            gw = fcm_config.gateway()
            for token in tokens:
                res = gw.enviar(token, titulo, cuerpo, datos=datos)
                if res.get("ok"):
                    ok += 1
                else:
                    logger.warning("push FCM no entregado a %s: %s", token, res.get("motivo"))
        except Exception as ex:
            logger.error("envío push FCM: %s", ex)

    return {"entregado": entregado, "dispositivos": intentados,
            "push_real": {"intentados": intentados, "ok": ok}, "titulo": titulo}


__all__ = ["registrar_dispositivo", "dispositivos", "enviar"]
