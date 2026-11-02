"""
Tareas de empleados por tienda — encargos que un SUPERADMIN programa (conectado a la tienda destino vía
`SelectorTiendaDialog`) para el personal OPERARIO/ADMINISTRADOR de esa tienda concreta.

Distinto del Programador de Jobs (`services.scheduler` + `panel_jobs.py`): aquello son tareas de FONDO
internas de la app (jobs Python que se ejecutan solos); esto son encargos para una PERSONA (p. ej.
"registrar la temperatura de las neveras cada mañana"), sin motor de aprobación — el propio empleado
resuelve la tarea marcándola como finalizada.
"""

import logging

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("services.tareas_empleados")

FRECUENCIAS = ("puntual", "diaria", "semanal", "mensual")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_tarea(id_tienda, titulo, *, descripcion=None, frecuencia=None, creado_por=None,
                id_empresa=None) -> dict:
    if not id_tienda:
        return {"ok": False, "error": "Selecciona primero la tienda destino."}
    titulo = (titulo or "").strip()
    if not titulo:
        return {"ok": False, "error": "El título de la tarea es obligatorio."}
    eid = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tareas_empleados (id_empresa, id_tienda, titulo, descripcion, "
                "frecuencia, creado_por) VALUES (%s,%s,%s,%s,%s,%s)",
                (eid, id_tienda, titulo, (descripcion or "").strip() or None, frecuencia, creado_por))
            tid = cur.lastrowid
        return {"ok": True, "id": tid}
    except Exception as e:
        logger.error("crear_tarea: %s", e)
        return {"ok": False, "error": str(e)}


def listar_tareas_tienda(id_tienda, *, id_empresa=None, estado=None, incluir_canceladas=False) -> list:
    """`incluir_canceladas=False` (por defecto): una tarea cancelada desaparece de este listado tanto
    para quien la creó (SUPERADMIN) como para quien la recibía (operario/administrador) — cancelar
    la retira de TODAS las vistas, no solo la oculta al personal. Se puede pedir explícitamente con
    `incluir_canceladas=True` si algún día hace falta un histórico."""
    if not id_tienda:
        return []
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id, titulo, descripcion, frecuencia, estado, creado_por, completado_por, "
                   "fecha_completado, fecha_creacion FROM tareas_empleados "
                   "WHERE id_empresa=%s AND id_tienda=%s")
            params = [eid, id_tienda]
            if estado:
                sql += " AND estado=%s"
                params.append(estado)
            elif not incluir_canceladas:
                sql += " AND estado != 'cancelada'"
            sql += " ORDER BY (estado='pendiente') DESC, fecha_creacion DESC"
            cur.execute(sql, tuple(params))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_tareas_tienda: %s", e)
        return []


def completar_tarea(id_tarea, *, usuario_id, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tareas_empleados SET estado='completada', completado_por=%s, "
                "fecha_completado=NOW() WHERE id=%s AND id_empresa=%s AND estado='pendiente'",
                (usuario_id, id_tarea, eid))
            afectadas = cur.rowcount
        if afectadas == 0:
            return {"ok": False, "error": "La tarea ya no está pendiente."}
        return {"ok": True}
    except Exception as e:
        logger.error("completar_tarea: %s", e)
        return {"ok": False, "error": str(e)}


def actualizar_descripcion(id_tarea, descripcion, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            # No se comprueba `rowcount`: PyMySQL (sin CLIENT_FOUND_ROWS) lo reporta como filas
            # REALMENTE modificadas, no encontradas — guardar la misma descripción que ya había
            # daría 0 y se leería como "no encontrada" siendo falso.
            cur.execute(
                "UPDATE tareas_empleados SET descripcion=%s WHERE id=%s AND id_empresa=%s",
                ((descripcion or "").strip() or None, id_tarea, eid))
        return {"ok": True}
    except Exception as e:
        logger.error("actualizar_descripcion: %s", e)
        return {"ok": False, "error": str(e)}


def cancelar_tarea(id_tarea, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tareas_empleados SET estado='cancelada' WHERE id=%s AND id_empresa=%s "
                "AND estado='pendiente'", (id_tarea, eid))
            afectadas = cur.rowcount
        if afectadas == 0:
            return {"ok": False, "error": "La tarea ya no está pendiente."}
        return {"ok": True}
    except Exception as e:
        logger.error("cancelar_tarea: %s", e)
        return {"ok": False, "error": str(e)}
