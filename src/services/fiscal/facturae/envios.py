"""
Cola/seguimiento de envíos Facturae (C3.4.4) — tabla `facturae_envios`.

Actúa como cola propia (estado + backoff) SIN tocar el worker congelado de C3.2.
Multiempresa por id_empresa.
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("fiscal.facturae.envios")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def crear(venta_id, numero_factura, canal="face", version="3.2.2", id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO facturae_envios (id_empresa, venta_id, numero_factura, version, canal) "
                "VALUES (%s,%s,%s,%s,%s)", (id_empresa, venta_id, numero_factura, version, canal))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear envio: %s", e)
        return None


def listar(estado="pendiente", id_empresa=None, listos=False, limite=100) -> list:
    id_empresa = _empresa(id_empresa)
    extra = " AND (proximo_intento IS NULL OR proximo_intento <= NOW())" if listos else ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturae_envios WHERE id_empresa=%s AND estado=%s"
                        + extra + " ORDER BY id LIMIT %s", (id_empresa, estado, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar envios: %s", e)
        return []


def obtener(id_envio):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturae_envios WHERE id=%s", (id_envio,))
            r = cur.fetchone()
            return _filas_a_dicts(cur, [r])[0] if r else None
    except Exception as e:
        logger.error("obtener envio(%s): %s", id_envio, e)
        return None


def actualizar(id_envio, estado, numero_registro=None, csv=None, error=None,
               proximo_intento=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE facturae_envios SET estado=%s, intentos=intentos+1, "
                "numero_registro=COALESCE(%s, numero_registro), csv=COALESCE(%s, csv), "
                "ultimo_error=%s, proximo_intento=%s WHERE id=%s",
                (estado, numero_registro, csv, (error or "")[:500] or None,
                 proximo_intento, id_envio))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar envio(%s): %s", id_envio, e)
        return False
