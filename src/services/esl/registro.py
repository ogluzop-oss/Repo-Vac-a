"""
Registro de etiquetas electrónicas: mapeo etiqueta física ↔ artículo (label_id ↔ codigo_articulo).
Aislamiento estricto por (empresa, tienda). Una etiqueta recién vinculada queda 'PENDIENTE' (aún no
sincronizada).
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.esl.config import _ctx

logger = logging.getLogger("esl.registro")


def vincular(codigo, label_id, proveedor=None, plantilla=None, id_empresa=None, id_tienda=None):
    """Vincula (o reasigna) una etiqueta a un artículo. Valida que el artículo exista. Devuelve id/True."""
    e, t = _ctx(id_empresa, id_tienda)
    codigo = (codigo or "").strip()
    label_id = str(label_id or "").strip()
    if not codigo or not label_id:
        return None
    from src.db.conexion import obtener_articulo
    if not obtener_articulo(codigo, id_empresa=e):     # propaga la empresa (obtener_articulo es tenant-aware)
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO esl_labels (id_empresa,id_tienda,codigo_articulo,label_id,proveedor,plantilla,"
                "estado) VALUES (%s,%s,%s,%s,%s,%s,'PENDIENTE') "
                "ON DUPLICATE KEY UPDATE codigo_articulo=VALUES(codigo_articulo),"
                "proveedor=VALUES(proveedor),plantilla=VALUES(plantilla),estado='PENDIENTE',"
                "precio_sincronizado=NULL,ultimo_error=NULL",
                (e, t, codigo, label_id, proveedor, plantilla))
            return cur.lastrowid or True
    except Exception as ex:
        logger.error("vincular: %s", ex)
        return None


def desvincular(label_id, id_empresa=None, id_tienda=None):
    e, t = _ctx(id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM esl_labels WHERE id_empresa=%s AND id_tienda=%s AND label_id=%s",
                        (e, t, str(label_id)))
            return True
    except Exception as ex:
        logger.error("desvincular: %s", ex)
        return False


def listar(estado=None, id_empresa=None, id_tienda=None):
    e, t = _ctx(id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM esl_labels WHERE id_empresa=%s AND id_tienda=%s"
            params = [e, t]
            if estado:
                q += " AND estado=%s"
                params.append(estado)
            q += " ORDER BY codigo_articulo"
            cur.execute(q, tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as ex:
        logger.error("listar: %s", ex)
        return []


def etiquetas_de_articulo(codigo, id_empresa=None, id_tienda=None):
    e, t = _ctx(id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM esl_labels WHERE id_empresa=%s AND id_tienda=%s AND codigo_articulo=%s",
                        (e, t, (codigo or "").strip()))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as ex:
        logger.error("etiquetas_de_articulo: %s", ex)
        return []
