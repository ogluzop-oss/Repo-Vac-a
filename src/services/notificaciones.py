"""
Notificaciones empresariales (FASE COM-1).

Sistema central de notificaciones persistentes, multiempresa y auditado. Una notificación tiene
N destinatarios (por usuario y/o por rol). La lectura se registra por usuario. Best-effort: la
emisión nunca rompe la operación que la dispara (se usa desde Workflow/AEAT/Tesorería/Inventario).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("notificaciones")

PRIORIDADES = ("baja", "normal", "alta", "critica")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def emitir(tipo, titulo, mensaje="", *, prioridad="normal", modulo=None, usuarios=None,
           roles=None, ref_entidad=None, ref_id=None, id_empresa=None) -> int | None:
    """Crea una notificación y la dirige a `usuarios` (ids) y/o `roles` (perfiles). Devuelve id."""
    id_empresa = _emp(id_empresa)
    if prioridad not in PRIORIDADES:
        prioridad = "normal"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO notificaciones (id_empresa, tipo, modulo, titulo, mensaje, "
                        "prioridad, ref_entidad, ref_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, tipo, modulo, titulo, mensaje, prioridad, ref_entidad,
                         (str(ref_id) if ref_id is not None else None)))
            nid = cur.lastrowid
            for uid in (usuarios or []):
                cur.execute("INSERT INTO notificaciones_destinatarios (id_empresa, id_notificacion, "
                            "usuario_destino) VALUES (%s,%s,%s)", (id_empresa, nid, uid))
            for rol in (roles or []):
                cur.execute("INSERT INTO notificaciones_destinatarios (id_empresa, id_notificacion, "
                            "rol_destino) VALUES (%s,%s,%s)", (id_empresa, nid, str(rol).upper()))
            conn.commit()
        _audit("NOTIFICACION_EMITIDA", f"id={nid} {tipo} prio={prioridad}")
        return nid
    except Exception as e:
        logger.error("emitir: %s", e)
        return None


def marcar_leida(id_notificacion, usuario, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO notificaciones_lecturas (id_empresa, id_notificacion, "
                        "usuario) VALUES (%s,%s,%s)", (id_empresa, id_notificacion, usuario))
            cur.execute("UPDATE notificaciones_destinatarios SET estado='leida' WHERE "
                        "id_notificacion=%s AND usuario_destino=%s", (id_notificacion, usuario))
            conn.commit()
        return True
    except Exception as e:
        logger.error("marcar_leida: %s", e)
        return False


def pendientes_usuario(usuario, *, perfil=None, id_empresa=None, limite=200) -> list:
    """Notificaciones no leídas dirigidas al usuario (por id) o a su rol (perfil)."""
    id_empresa = _emp(id_empresa)
    if isinstance(usuario, dict):
        perfil = perfil or usuario.get("perfil")
        usuario = usuario.get("id")
    perfil = (perfil or "").upper()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT n.* FROM notificaciones n "
                "JOIN notificaciones_destinatarios d ON d.id_notificacion=n.id "
                "WHERE n.id_empresa=%s AND (d.usuario_destino=%s OR d.rol_destino=%s) "
                "AND NOT EXISTS (SELECT 1 FROM notificaciones_lecturas l "
                "  WHERE l.id_notificacion=n.id AND l.usuario=%s) "
                "ORDER BY FIELD(n.prioridad,'critica','alta','normal','baja'), n.fecha_creacion DESC "
                "LIMIT %s", (id_empresa, usuario, perfil, usuario, int(limite)))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("pendientes_usuario: %s", e)
        return []


def listar(*, modulo=None, prioridad=None, id_empresa=None, limite=500) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM notificaciones WHERE id_empresa=%s"
    p = [id_empresa]
    if modulo:
        q += " AND modulo=%s"; p.append(modulo)
    if prioridad:
        q += " AND prioridad=%s"; p.append(prioridad)
    q += " ORDER BY fecha_creacion DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def eliminar(id_notificacion, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM notificaciones_lecturas WHERE id_notificacion=%s", (id_notificacion,))
            cur.execute("DELETE FROM notificaciones_destinatarios WHERE id_notificacion=%s", (id_notificacion,))
            cur.execute("DELETE FROM notificaciones WHERE id=%s AND id_empresa=%s", (id_notificacion, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("eliminar: %s", e)
        return False


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "notificaciones", detalle)
    except Exception:
        pass
