"""
Workflow / BPM — persistencia (FASE WF-1).

CRUD de definiciones, pasos, reglas, instancias, tareas, log y delegaciones. La lógica del
motor (resolución de aprobadores, reglas, avance) vive en src/services/workflow/workflow_engine.py.
Multiempresa: definiciones e instancias acotadas por id_empresa.
"""

import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("workflow.db")


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


def _filas(cur):
    return [_fila(cur, r) for r in cur.fetchall()]


def _uno(cur):
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


# ── Definiciones / pasos / reglas ────────────────────────────────────────────
def crear_definicion(codigo, nombre, entidad, *, descripcion=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_definiciones (id_empresa, codigo, nombre, descripcion, entidad) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "descripcion=VALUES(descripcion), entidad=VALUES(entidad), activo=1",
                        (id_empresa, codigo, nombre, descripcion, entidad))
            conn.commit()
            cur.execute("SELECT id FROM wf_definiciones WHERE id_empresa=%s AND codigo=%s AND version=1",
                        (id_empresa, codigo))
            return _uno(cur)
    except Exception as e:
        logger.error("crear_definicion: %s", e)
        return None


def anadir_paso(id_definicion, orden, nombre, *, tipo_paso="aprobacion", permiso_requerido=None,
                rol_requerido=None, grupo_requerido=None, usuarios_minimos=1, obligatorio=1,
                sla_horas=None) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_pasos (id_definicion, orden, nombre, tipo_paso, "
                        "permiso_requerido, rol_requerido, grupo_requerido, usuarios_minimos, "
                        "obligatorio, sla_horas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_definicion, orden, nombre, tipo_paso, permiso_requerido, rol_requerido,
                         grupo_requerido, usuarios_minimos, obligatorio, sla_horas))
            pid = cur.lastrowid
            conn.commit()
            return pid
    except Exception as e:
        logger.error("anadir_paso: %s", e)
        return None


def anadir_regla(id_definicion, condicion, operador, valor, *, id_paso=None, accion="activar_paso") -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_reglas (id_definicion, id_paso, condicion, operador, valor, accion) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_definicion, id_paso, condicion, operador, str(valor), accion))
            rid = cur.lastrowid
            conn.commit()
            return rid
    except Exception as e:
        logger.error("anadir_regla: %s", e)
        return None


def definicion_activa(entidad, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM wf_definiciones WHERE id_empresa=%s AND entidad=%s AND activo=1 "
                        "ORDER BY version DESC LIMIT 1", (id_empresa, entidad))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("definicion_activa: %s", e)
        return None


def pasos_de(id_definicion) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM wf_pasos WHERE id_definicion=%s ORDER BY orden", (id_definicion,))
            return _filas(cur)
    except Exception as e:
        logger.error("pasos_de: %s", e)
        return []


def reglas_de(id_definicion) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM wf_reglas WHERE id_definicion=%s", (id_definicion,))
            return _filas(cur)
    except Exception as e:
        logger.error("reglas_de: %s", e)
        return []


# ── Instancias / tareas ──────────────────────────────────────────────────────
def crear_instancia(id_definicion, entidad, entidad_id, *, contexto=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM wf_instancias WHERE id_empresa=%s AND entidad=%s AND "
                        "entidad_id=%s AND id_definicion=%s",
                        (id_empresa, entidad, str(entidad_id), id_definicion))
            ya = _uno(cur)
            if ya:
                return ya                       # idempotente: una instancia por (entidad,id,def)
            cur.execute("INSERT INTO wf_instancias (id_empresa, id_definicion, entidad, entidad_id, "
                        "contexto) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, id_definicion, entidad, str(entidad_id),
                         json.dumps(contexto or {}, default=str)))
            iid = cur.lastrowid
            conn.commit()
            return iid
    except Exception as e:
        logger.error("crear_instancia: %s", e)
        return None


def obtener_instancia(id_instancia, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM wf_instancias WHERE id=%s AND id_empresa=%s", (id_instancia, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
            try:
                d["contexto"] = json.loads(d.get("contexto") or "{}")
            except Exception:
                d["contexto"] = {}
            return d
    except Exception as e:
        logger.error("obtener_instancia: %s", e)
        return None


def instancia_por_entidad(entidad, entidad_id, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM wf_instancias WHERE id_empresa=%s AND entidad=%s AND entidad_id=%s "
                        "ORDER BY id DESC LIMIT 1", (id_empresa, entidad, str(entidad_id)))
            iid = _uno(cur)
        return obtener_instancia(iid, id_empresa) if iid else None
    except Exception as e:
        logger.error("instancia_por_entidad: %s", e)
        return None


def actualizar_instancia(id_instancia, *, estado=None, paso_actual=None, cerrar=False, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    sets, vals = [], []
    if estado is not None:
        sets.append("estado=%s"); vals.append(estado)
    if paso_actual is not None:
        sets.append("paso_actual=%s"); vals.append(paso_actual)
    if cerrar:
        sets.append("fecha_fin=NOW()")
    if not sets:
        return False
    vals += [id_instancia, id_empresa]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE wf_instancias SET {', '.join(sets)} WHERE id=%s AND id_empresa=%s", vals)
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_instancia: %s", e)
        return False


def crear_tarea(id_instancia, id_paso, *, asignado_rol=None, asignado_grupo=None,
                asignado_usuario=None, permiso_requerido=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_tareas (id_empresa, id_instancia, id_paso, asignado_rol, "
                        "asignado_grupo, asignado_usuario, permiso_requerido) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_instancia, id_paso, asignado_rol, asignado_grupo,
                         asignado_usuario, permiso_requerido))
            tid = cur.lastrowid
            conn.commit()
            return tid
    except Exception as e:
        logger.error("crear_tarea: %s", e)
        return None


def obtener_tarea(id_tarea, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM wf_tareas WHERE id=%s AND id_empresa=%s", (id_tarea, id_empresa))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_tarea: %s", e)
        return None


def resolver_tarea(id_tarea, estado, aprobado_por, comentario=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE wf_tareas SET estado=%s, aprobado_por=%s, comentario=%s, "
                        "fecha_resolucion=NOW() WHERE id=%s AND id_empresa=%s",
                        (estado, aprobado_por, comentario, id_tarea, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("resolver_tarea: %s", e)
        return False


def tareas_de_instancia(id_instancia, *, estado=None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM wf_tareas WHERE id_instancia=%s AND id_empresa=%s"
    p = [id_instancia, id_empresa]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY id"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("tareas_de_instancia: %s", e)
        return []


def tareas_pendientes(*, estado="PENDIENTE", id_empresa=None, limite=500) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT t.*, i.entidad, i.entidad_id FROM wf_tareas t "
                        "JOIN wf_instancias i ON i.id=t.id_instancia "
                        "WHERE t.id_empresa=%s AND t.estado=%s ORDER BY t.fecha_creacion LIMIT %s",
                        (id_empresa, estado, int(limite)))
            return _filas(cur)
    except Exception as e:
        logger.error("tareas_pendientes: %s", e)
        return []


# ── Log / delegaciones ───────────────────────────────────────────────────────
def log(id_instancia, accion, *, usuario=None, detalle=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_log (id_empresa, id_instancia, accion, usuario, detalle) "
                        "VALUES (%s,%s,%s,%s,%s)", (id_empresa, id_instancia, accion, usuario, detalle))
            conn.commit()
        return True
    except Exception as e:
        logger.error("log: %s", e)
        return False


def crear_delegacion(usuario_origen, usuario_destino, *, fecha_inicio=None, fecha_fin=None,
                     id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO wf_delegaciones (id_empresa, usuario_origen, usuario_destino, "
                        "fecha_inicio, fecha_fin) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, usuario_origen, usuario_destino, fecha_inicio, fecha_fin))
            did = cur.lastrowid
            conn.commit()
            return did
    except Exception as e:
        logger.error("crear_delegacion: %s", e)
        return None


def delegados_de(usuario_origen, id_empresa=None) -> list:
    """Usuarios destino activos a los que `usuario_origen` ha delegado (vigentes hoy)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT usuario_destino FROM wf_delegaciones WHERE id_empresa=%s AND "
                        "usuario_origen=%s AND activa=1 AND (fecha_inicio IS NULL OR fecha_inicio<=CURDATE()) "
                        "AND (fecha_fin IS NULL OR fecha_fin>=CURDATE())", (id_empresa, usuario_origen))
            return [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
    except Exception as e:
        logger.error("delegados_de: %s", e)
        return []
