import logging

from .conexion import obtener_conexion

logger = logging.getLogger("reabastecimiento_db")


# ── CONFIG ──────────────────────────────────────────────────────────────────

def listar_config() -> list:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rc.codigo, a.nombre,
                           COALESCE(a.Stock_tienda,0) + COALESCE(a.Stock_total,0) AS stock_actual,
                           rc.umbral_min, rc.stock_objetivo,
                           rc.origen, rc.automatico
                    FROM reab_config rc
                    JOIN articulos a ON a.codigo = rc.codigo
                    ORDER BY a.nombre ASC
                """)
                rows = cur.fetchall()
                return [
                    {
                        "codigo": r[0], "nombre": r[1], "stock_actual": r[2],
                        "umbral_min": r[3], "stock_objetivo": r[4],
                        "origen": r[5], "automatico": bool(r[6]),
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"Error listando config reabastecimiento: {e}")
        return []


def upsert_config(codigo: str, umbral_min: int, stock_objetivo: int,
                  origen: str = "ALMACÉN CENTRAL", automatico: bool = True) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reab_config (codigo, umbral_min, stock_objetivo, origen, automatico)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        umbral_min = VALUES(umbral_min),
                        stock_objetivo = VALUES(stock_objetivo),
                        origen = VALUES(origen),
                        automatico = VALUES(automatico)
                """, (codigo, umbral_min, stock_objetivo, origen, int(automatico)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error guardando config reabastecimiento: {e}")
        return False


def eliminar_config(codigo: str) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reab_config WHERE codigo=%s", (codigo,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error eliminando config reabastecimiento: {e}")
        return False


def obtener_config(codigo: str) -> dict | None:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT umbral_min, stock_objetivo, origen, automatico "
                    "FROM reab_config WHERE codigo=%s",
                    (codigo,)
                )
                r = cur.fetchone()
                if r:
                    return {"umbral_min": r[0], "stock_objetivo": r[1],
                            "origen": r[2], "automatico": bool(r[3])}
    except Exception as e:
        logger.error(f"Error obteniendo config: {e}")
    return None


# ── PROPUESTAS ───────────────────────────────────────────────────────────────

def crear_propuesta(codigo: str, nombre: str, cantidad: int,
                    origen: str, stock_actual: int, stock_objetivo: int) -> int | None:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reab_propuestas
                        (codigo, nombre_articulo, cantidad, origen, stock_actual,
                         stock_objetivo, estado)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pendiente')
                """, (codigo, nombre, cantidad, origen, stock_actual, stock_objetivo))
                pid = cur.lastrowid
            conn.commit()
            return pid
    except Exception as e:
        logger.error(f"Error creando propuesta: {e}")
    return None


def listar_propuestas(estados: tuple = None) -> list:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                if estados:
                    placeholders = ",".join(["%s"] * len(estados))
                    cur.execute(
                        f"SELECT id, codigo, nombre_articulo, cantidad, origen, "
                        f"stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                        f"FROM reab_propuestas WHERE estado IN ({placeholders}) "
                        f"ORDER BY fecha_creacion DESC",
                        estados
                    )
                else:
                    cur.execute(
                        "SELECT id, codigo, nombre_articulo, cantidad, origen, "
                        "stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                        "FROM reab_propuestas ORDER BY fecha_creacion DESC"
                    )
                rows = cur.fetchall()
                return [
                    {
                        "id": r[0], "codigo": r[1], "nombre": r[2],
                        "cantidad": r[3], "origen": r[4],
                        "stock_actual": r[5], "stock_objetivo": r[6],
                        "estado": r[7], "fecha_creacion": r[8], "fecha_accion": r[9],
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"Error listando propuestas: {e}")
        return []


def cambiar_estado_propuesta(propuesta_id: int, nuevo_estado: str) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE reab_propuestas SET estado=%s, fecha_accion=NOW() WHERE id=%s",
                    (nuevo_estado, propuesta_id)
                )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error cambiando estado propuesta: {e}")
        return False


def marcar_articulos_recibidos(codigos: list) -> int:
    """Cambia a 'recibido' todas las propuestas activas de los artículos indicados."""
    if not codigos:
        return 0
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(codigos))
                cur.execute(
                    f"UPDATE reab_propuestas SET estado='recibido', fecha_accion=NOW() "
                    f"WHERE codigo IN ({placeholders}) "
                    f"AND estado IN ('pendiente','aprobado','enviado')",
                    codigos,
                )
                count = cur.rowcount
            conn.commit()
            return count
    except Exception as e:
        logger.error(f"Error marcando artículos como recibidos: {e}")
        return 0


def propuesta_pendiente_existe(codigo: str) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM reab_propuestas "
                    "WHERE codigo=%s AND estado IN ('pendiente','aprobado','enviado')",
                    (codigo,)
                )
                r = cur.fetchone()
                return bool(r and r[0] > 0)
    except Exception as e:
        logger.error(f"Error comprobando propuesta existente: {e}")
    return False


def obtener_propuesta(propuesta_id: int) -> dict | None:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, codigo, nombre_articulo, cantidad, origen, "
                    "stock_actual, stock_objetivo, estado, fecha_creacion, fecha_accion "
                    "FROM reab_propuestas WHERE id=%s",
                    (propuesta_id,)
                )
                r = cur.fetchone()
                if r:
                    return {
                        "id": r[0], "codigo": r[1], "nombre": r[2],
                        "cantidad": r[3], "origen": r[4],
                        "stock_actual": r[5], "stock_objetivo": r[6],
                        "estado": r[7], "fecha_creacion": r[8], "fecha_accion": r[9],
                    }
    except Exception as e:
        logger.error(f"Error obteniendo propuesta: {e}")
    return None


# ── PROGRAMACIÓN DE ENVÍOS ───────────────────────────────────────────────────

def cargar_schedule() -> dict:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT email, dias, hora, minuto, ultima_envio, smtp_user, smtp_pass "
                    "FROM reab_schedule LIMIT 1"
                )
                r = cur.fetchone()
                if r:
                    return {
                        "email": r[0] or "", "dias": r[1] or "",
                        "hora": int(r[2]), "minuto": int(r[3]),
                        "ultima_envio": r[4],
                        "smtp_user": r[5] or "", "smtp_pass": r[6] or "",
                    }
    except Exception as e:
        logger.error(f"Error cargando schedule: {e}")
    return {"email": "", "dias": "", "hora": 8, "minuto": 0, "ultima_envio": None,
            "smtp_user": "", "smtp_pass": ""}


def guardar_schedule(email: str, dias: str, hora: int, minuto: int,
                     smtp_user: str = "", smtp_pass: str = "") -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM reab_schedule LIMIT 1")
                r = cur.fetchone()
                if r:
                    cur.execute(
                        "UPDATE reab_schedule SET email=%s, dias=%s, hora=%s, minuto=%s, "
                        "smtp_user=%s, smtp_pass=%s WHERE id=%s",
                        (email, dias, hora, minuto, smtp_user, smtp_pass, r[0])
                    )
                else:
                    cur.execute(
                        "INSERT INTO reab_schedule (email, dias, hora, minuto, smtp_user, smtp_pass) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (email, dias, hora, minuto, smtp_user, smtp_pass)
                    )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error guardando schedule: {e}")
        return False


def marcar_envio_hoy() -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE reab_schedule SET ultima_envio = CURDATE()")
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error marcando envio: {e}")
        return False
