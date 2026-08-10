"""
Gestión de proyectos — CRUD de proyectos. Multiempresa. Eliminar un proyecto arrastra sus tareas, horas
y costes (limpieza en cascada aplicativa, sin FK). Toda la lógica vive aquí; la GUI solo orquesta.
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("proyectos")

ESTADOS = ("planificado", "en_curso", "pausado", "cerrado", "cancelado")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def crear_proyecto(nombre, *, descripcion=None, id_cliente=None, responsable=None, fecha_inicio=None,
                   fecha_fin_prevista=None, presupuesto=0, coste_hora_defecto=0, estado="planificado",
                   id_empresa=None):
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    if estado not in ESTADOS:
        estado = "planificado"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proyectos (id_empresa,nombre,descripcion,estado,id_cliente,responsable,"
                "fecha_inicio,fecha_fin_prevista,presupuesto,coste_hora_defecto) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (_emp(id_empresa), nombre, descripcion, estado, id_cliente, responsable, fecha_inicio,
                 fecha_fin_prevista, float(presupuesto or 0), float(coste_hora_defecto or 0)))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_proyecto: %s", e)
        return None


def listar_proyectos(id_empresa=None, solo_activos=True):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM proyectos WHERE id_empresa=%s"
            if solo_activos:
                q += " AND activo=1"
            q += " ORDER BY creado DESC"
            cur.execute(q, (_emp(id_empresa),))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_proyectos: %s", e)
        return []


def obtener_proyecto(id_proyecto, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyectos WHERE id=%s AND id_empresa=%s",
                        (id_proyecto, _emp(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_proyecto: %s", e)
        return None


def actualizar_proyecto(id_proyecto, id_empresa=None, **campos):
    permitidos = ("nombre", "descripcion", "estado", "id_cliente", "responsable", "fecha_inicio",
                  "fecha_fin_prevista", "presupuesto", "coste_hora_defecto", "activo")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE proyectos SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_proyecto, _emp(id_empresa)))
            return True
    except Exception as e:
        logger.error("actualizar_proyecto: %s", e)
        return False


def eliminar_proyecto(id_proyecto, id_empresa=None):
    """Elimina el proyecto y sus tareas/horas/costes (cascada aplicativa)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("proyecto_costes", "proyecto_horas", "proyecto_tareas"):
                cur.execute(f"DELETE FROM {t} WHERE id_proyecto=%s AND id_empresa=%s", (id_proyecto, eid))
            cur.execute("DELETE FROM proyectos WHERE id=%s AND id_empresa=%s", (id_proyecto, eid))
            return True
    except Exception as e:
        logger.error("eliminar_proyecto: %s", e)
        return False
