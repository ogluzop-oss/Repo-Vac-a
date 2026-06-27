"""
Tareas empresariales (FASE COM-7).

Tareas generales (independientes de wf_tareas del Workflow): asignación, reasignación,
seguimiento, comentarios. Multiempresa y auditado. Emite notificación al asignar.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("tareas")
ESTADOS = ("pendiente", "en_progreso", "bloqueada", "completada", "cancelada")


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


def crear_tarea(titulo, *, descripcion=None, asignado_a=None, creado_por=None, prioridad="normal",
                vencimiento=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO tareas (id_empresa, titulo, descripcion, asignado_a, creado_por, "
                        "prioridad, vencimiento) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, titulo, descripcion, asignado_a, creado_por, prioridad, vencimiento))
            tid = cur.lastrowid
            conn.commit()
        _audit("TAREA_ASIGNADA", f"id={tid} → {asignado_a}")
        _notificar(asignado_a, titulo, id_empresa)
        return tid
    except Exception as e:
        logger.error("crear_tarea: %s", e)
        return None


def reasignar(id_tarea, nuevo_asignado, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE tareas SET asignado_a=%s WHERE id=%s AND id_empresa=%s",
                        (nuevo_asignado, id_tarea, id_empresa))
            conn.commit()
        _audit("TAREA_ASIGNADA", f"id={id_tarea} reasignada → {nuevo_asignado}")
        _notificar(nuevo_asignado, f"Tarea #{id_tarea} reasignada", id_empresa)
        return True
    except Exception as e:
        logger.error("reasignar: %s", e)
        return False


def cambiar_estado(id_tarea, estado, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado}")
    cierre = ", fecha_cierre=NOW()" if estado in ("completada", "cancelada") else ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE tareas SET estado=%s{cierre} WHERE id=%s AND id_empresa=%s",
                        (estado, id_tarea, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return False


def comentar(id_tarea, usuario, comentario, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO tareas_comentarios (id_empresa, id_tarea, usuario, comentario) "
                        "VALUES (%s,%s,%s,%s)", (id_empresa, id_tarea, usuario, comentario))
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.error("comentar: %s", e)
        return None


def tareas_de(asignado_a, *, estado=None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM tareas WHERE id_empresa=%s AND asignado_a=%s"
    p = [id_empresa, asignado_a]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY FIELD(prioridad,'critica','alta','normal','baja'), vencimiento"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("tareas_de: %s", e)
        return []


def _notificar(asignado_a, titulo, id_empresa):
    if not asignado_a:
        return
    try:
        from src.services import notificaciones
        notificaciones.emitir("tarea", "Nueva tarea asignada", titulo, modulo="tareas",
                              usuarios=[asignado_a], id_empresa=id_empresa)
    except Exception:
        pass


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "tareas", detalle)
    except Exception:
        pass
