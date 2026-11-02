"""
Configuración de hardware RFID real (lector Zebra FX/RFD vía LLRP) — tabla `rfid_lectores`
(migr. 0299). UNA fila por (empresa, centro); `id_centro=''` es la config EMPRESA-WIDE, usada
cuando no hay una fila más específica para el centro activo (mismo criterio de alcance que
`camaras`). Sin credenciales: LLRP estándar (puerto 5084) no las necesita — ver docstring de la
migración.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("rfid_hardware.db")

PUERTO_LLRP_DEFECTO = 5084


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def obtener_config(id_empresa, id_centro=None) -> dict:
    """Config efectiva del lector RFID: la fila del CENTRO activo si existe, si no la fila
    EMPRESA-WIDE (`id_centro=''`), si no un valor por defecto honesto (modo simulado, sin IP —
    nunca se inventa una dirección). `id_centro=None`/`''` salta directo a la empresa-wide."""
    centro = (id_centro or "").strip()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if centro:
                cur.execute(
                    "SELECT * FROM rfid_lectores WHERE id_empresa=%s AND id_centro=%s AND activo=1",
                    (id_empresa, centro))
                row = cur.fetchone()
                if row:
                    return _fila(cur, row)
            cur.execute(
                "SELECT * FROM rfid_lectores WHERE id_empresa=%s AND id_centro='' AND activo=1",
                (id_empresa,))
            row = cur.fetchone()
            if row:
                return _fila(cur, row)
    except Exception as e:
        logger.error("obtener_config(%s,%s): %s", id_empresa, id_centro, e)
    return {"modo": "simulado", "ip": None, "puerto": PUERTO_LLRP_DEFECTO, "nombre": "Lector RFID"}


def guardar_config(id_empresa, id_centro, *, nombre=None, modo="simulado", ip=None,
                   puerto=PUERTO_LLRP_DEFECTO) -> dict:
    """Alta/actualización (upsert) de la config del lector para (empresa, centro). `modo` fuera de
    {'simulado','fisico'} se normaliza a 'simulado' (nunca se guarda un modo inválido que el
    resolutor no sepa interpretar)."""
    centro = (id_centro or "").strip()
    modo = modo if modo in ("simulado", "fisico") else "simulado"
    ip = (ip or "").strip() or None
    try:
        puerto = int(puerto) if puerto else PUERTO_LLRP_DEFECTO
    except (TypeError, ValueError):
        puerto = PUERTO_LLRP_DEFECTO
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rfid_lectores (id_empresa, id_centro, nombre, modo, ip, puerto, activo) "
                "VALUES (%s,%s,%s,%s,%s,%s,1) "
                "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), modo=VALUES(modo), ip=VALUES(ip), "
                "puerto=VALUES(puerto), activo=1",
                (id_empresa, centro, nombre or "Lector RFID", modo, ip, puerto))
            conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("guardar_config(%s,%s): %s", id_empresa, id_centro, e)
        return {"ok": False, "error": "error_interno"}


def eliminar_config(id_empresa, id_centro) -> bool:
    """Desactiva (no borra físicamente) la config de un centro — vuelve a caer al fallback
    empresa-wide o a simulado, sin perder el historial de qué IP se usó."""
    centro = (id_centro or "").strip()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE rfid_lectores SET activo=0 WHERE id_empresa=%s AND id_centro=%s",
                        (id_empresa, centro))
            conn.commit()
        return True
    except Exception as e:
        logger.error("eliminar_config(%s,%s): %s", id_empresa, id_centro, e)
        return False
