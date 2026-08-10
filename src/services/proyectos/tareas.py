"""
Tareas de proyecto — modelo Kanban (estado = columna, `orden` = posición) + fechas para el cronograma
(Gantt). `mover_tarea` cambia de columna/posición (drag del tablero). Multiempresa.
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.proyectos.proyectos import _emp

logger = logging.getLogger("proyectos.tareas")

# Columnas del tablero Kanban (orden fijo, de izquierda a derecha).
COLUMNAS = ("pendiente", "en_curso", "en_revision", "hecho")
COLUMNA_ETIQUETA = {"pendiente": "Pendiente", "en_curso": "En curso",
                    "en_revision": "En revisión", "hecho": "Hecho"}
PRIORIDADES = ("baja", "media", "alta")


def crear_tarea(id_proyecto, titulo, *, descripcion=None, estado="pendiente", responsable=None,
                prioridad="media", fecha_inicio=None, fecha_fin=None, id_empresa=None):
    titulo = (titulo or "").strip()
    if not titulo:
        return None
    if estado not in COLUMNAS:
        estado = "pendiente"
    if prioridad not in PRIORIDADES:
        prioridad = "media"
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(orden),-1)+1 FROM proyecto_tareas WHERE id_empresa=%s AND "
                        "id_proyecto=%s AND estado=%s", (eid, id_proyecto, estado))
            orden = int(cur.fetchone()[0] or 0)
            cur.execute("INSERT INTO proyecto_tareas (id_empresa,id_proyecto,titulo,descripcion,estado,"
                        "orden,responsable,prioridad,fecha_inicio,fecha_fin) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_proyecto, titulo, descripcion, estado, orden, responsable, prioridad,
                         fecha_inicio, fecha_fin))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_tarea: %s", e)
        return None


def listar_tareas(id_proyecto, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyecto_tareas WHERE id_empresa=%s AND id_proyecto=%s "
                        "ORDER BY estado, orden, id", (_emp(id_empresa), id_proyecto))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_tareas: %s", e)
        return []


def tablero(id_proyecto, id_empresa=None):
    """Devuelve {columna: [tareas]} en el orden de COLUMNAS (para pintar el Kanban)."""
    res = {c: [] for c in COLUMNAS}
    for t in listar_tareas(id_proyecto, id_empresa):
        res.setdefault(t["estado"], []).append(t)
    return res


def mover_tarea(id_tarea, nuevo_estado, *, orden=None, id_empresa=None):
    """Mueve una tarea a otra columna (y opcionalmente a una posición). Si no se da `orden`, va al final."""
    if nuevo_estado not in COLUMNAS:
        return False
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if orden is None:
                cur.execute("SELECT id_proyecto FROM proyecto_tareas WHERE id=%s AND id_empresa=%s",
                            (id_tarea, eid))
                row = cur.fetchone()
                if not row:
                    return False
                idp = row[0] if not isinstance(row, dict) else row["id_proyecto"]
                cur.execute("SELECT COALESCE(MAX(orden),-1)+1 FROM proyecto_tareas WHERE id_empresa=%s AND "
                            "id_proyecto=%s AND estado=%s", (eid, idp, nuevo_estado))
                orden = int(cur.fetchone()[0] or 0)
            cur.execute("UPDATE proyecto_tareas SET estado=%s, orden=%s WHERE id=%s AND id_empresa=%s",
                        (nuevo_estado, orden, id_tarea, eid))
            return True
    except Exception as e:
        logger.error("mover_tarea: %s", e)
        return False


def actualizar_tarea(id_tarea, id_empresa=None, **campos):
    permitidos = ("titulo", "descripcion", "estado", "orden", "responsable", "prioridad",
                  "fecha_inicio", "fecha_fin")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE proyecto_tareas SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_tarea, _emp(id_empresa)))
            return True
    except Exception as e:
        logger.error("actualizar_tarea: %s", e)
        return False


def eliminar_tarea(id_tarea, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proyecto_tareas WHERE id=%s AND id_empresa=%s",
                        (id_tarea, _emp(id_empresa)))
            return True
    except Exception as e:
        logger.error("eliminar_tarea: %s", e)
        return False


def cronograma(id_proyecto, id_empresa=None):
    """Tareas con fechas para el Gantt/cronograma (solo las que tienen fecha_inicio), ordenadas."""
    filas = [t for t in listar_tareas(id_proyecto, id_empresa) if t.get("fecha_inicio")]
    return sorted(filas, key=lambda t: (str(t.get("fecha_inicio")), str(t.get("fecha_fin") or "")))
