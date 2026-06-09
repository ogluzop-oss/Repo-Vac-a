"""
Capa de datos: ARTÍCULOS BANEADOS PARA DEVOLUCIÓN.

Artículos que, por política de empresa, NO admiten devolución bajo ningún concepto
(p. ej. ropa interior). Multi-tenant: cada baneo pertenece a una empresa.

El TPV consulta `esta_baneado(codigo)` durante el modo devolución para bloquear
automáticamente esos artículos y mostrar el motivo.
"""

import logging
from datetime import datetime

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("devol_ban_db")


def buscar_articulo(termino: str, limite: int = 20) -> list[dict]:
    """Busca artículos por código EAN (exacto) o por nombre (parcial)."""
    termino = (termino or "").strip()
    if not termino:
        return []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT codigo, nombre FROM articulos
                   WHERE codigo = %s OR nombre LIKE %s
                   ORDER BY (codigo = %s) DESC, nombre ASC
                   LIMIT %s""",
                (termino, f"%{termino}%", termino, limite),
            )
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error buscar_articulo(%s): %s", termino, e)
        return []


def banear_articulo(codigo: str, nombre: str = "", motivo: str = "",
                    usuario: str = "", id_empresa=None) -> bool:
    """Banea un artículo para devolución (upsert por empresa+código)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO devoluciones_baneados (id_empresa, codigo, nombre, motivo, usuario, fecha)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     nombre=VALUES(nombre), motivo=VALUES(motivo),
                     usuario=VALUES(usuario), fecha=VALUES(fecha)""",
                (id_empresa, str(codigo).strip(), nombre, motivo, usuario,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
        logger.info("Artículo baneado para devolución: %s", codigo)
        return True
    except Exception as e:
        logger.error("Error banear_articulo(%s): %s", codigo, e)
        return False


def desbanear_articulo(codigo=None, id_ban=None, id_empresa=None) -> bool:
    """Quita el baneo de un artículo (por id de fila o por código+empresa)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if id_ban is not None:
                cur.execute("DELETE FROM devoluciones_baneados WHERE id=%s", (id_ban,))
            else:
                cur.execute(
                    "DELETE FROM devoluciones_baneados WHERE id_empresa=%s AND codigo=%s",
                    (id_empresa, str(codigo).strip()),
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error desbanear_articulo(%s): %s", codigo or id_ban, e)
        return False


def listar_baneados(id_empresa=None) -> list[dict]:
    """Lista los artículos baneados de la empresa activa."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devoluciones_baneados WHERE id_empresa=%s ORDER BY fecha DESC",
                (id_empresa,),
            )
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_baneados: %s", e)
        return []


def esta_baneado(codigo: str, id_empresa=None) -> dict | None:
    """Devuelve el registro de baneo si el artículo está baneado, o None.
    Lo usa el TPV en modo devolución para bloquear el artículo."""
    if not codigo:
        return None
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devoluciones_baneados WHERE id_empresa=%s AND codigo=%s",
                (id_empresa, str(codigo).strip()),
            )
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error esta_baneado(%s): %s", codigo, e)
        return None
