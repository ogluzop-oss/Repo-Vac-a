"""
Capa de datos de CLIENTES (captura en el flujo de venta del TPV, multiempresa).

Cliente reutilizable (nombre, NIF, contacto) que se asocia a la venta. La venta
guarda además el nombre/NIF denormalizados para que el ticket y la búsqueda sean
robustos aunque el cliente cambie. Filtra por ``id_empresa``.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("clientes_db")


def _fila(cur, row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(zip([d[0] for d in cur.description], row))


def buscar_clientes(texto="", id_empresa=None, limite=50) -> list[dict]:
    """Busca clientes por nombre, NIF, teléfono o email."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            params = [id_empresa]
            sql = ("SELECT * FROM clientes WHERE id_empresa=%s AND estado='activo'")
            if texto:
                sql += " AND (nombre LIKE %s OR nif LIKE %s OR telefono LIKE %s OR email LIKE %s)"
                params += [f"%{texto}%"] * 4
            sql += " ORDER BY nombre ASC LIMIT %s"
            params.append(int(limite))
            cur.execute(sql, params)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Error buscar_clientes: %s", e)
        return []


def obtener_cliente(cliente_id) -> dict | None:
    if not cliente_id:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes WHERE id=%s", (cliente_id,))
            return _fila(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_cliente(%s): %s", cliente_id, e)
        return None


def crear_cliente(nombre, nif=None, telefono=None, email=None,
                  direccion=None, id_empresa=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    if not (nombre or "").strip():
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clientes (nombre, nif, telefono, email, direccion, id_empresa) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (nombre.strip(), (nif or None), (telefono or None),
                 (email or None), (direccion or None), id_empresa))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("Error crear_cliente: %s", e)
        return None
