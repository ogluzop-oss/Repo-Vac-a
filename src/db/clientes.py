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


# ── VTA.1 — CRUD completo + segmentación/crédito ──────────────────────────────
_PERMITIDOS = ("nombre", "nif", "telefono", "email", "direccion", "estado",
               "limite_credito", "riesgo_actual", "categoria", "segmento",
               "observaciones", "estado_crediticio")


def actualizar_cliente(cliente_id, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE clientes SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), cliente_id, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_cliente(%s): %s", cliente_id, e)
        return False


def eliminar_cliente(cliente_id, id_empresa=None) -> bool:
    """Baja LÓGICA (estado=inactivo) para no romper histórico de ventas."""
    return actualizar_cliente(cliente_id, id_empresa=id_empresa, estado="inactivo")


def activar_cliente(cliente_id, activo=True, id_empresa=None) -> bool:
    return actualizar_cliente(cliente_id, id_empresa=id_empresa,
                              estado="activo" if activo else "inactivo")


def listar_clientes(id_empresa=None, segmento=None, estado=None, limite=500) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    cond, params = ["id_empresa=%s"], [id_empresa]
    if segmento:
        cond.append("segmento=%s"); params.append(segmento)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM clientes WHERE {' AND '.join(cond)} "
                        "ORDER BY nombre LIMIT %s", (*params, int(limite)))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_clientes: %s", e)
        return []


# ── Contactos / Direcciones ───────────────────────────────────────────────────
def agregar_contacto(cliente_id, nombre, cargo=None, email=None, telefono=None,
                     id_empresa=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO clientes_contactos (id_cliente, id_empresa, nombre, cargo, "
                        "email, telefono) VALUES (%s,%s,%s,%s,%s,%s)",
                        (cliente_id, id_empresa, nombre, cargo, email, telefono))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("agregar_contacto: %s", e)
        return None


def listar_contactos(cliente_id, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes_contactos WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY id", (cliente_id, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_contactos: %s", e)
        return []


def agregar_direccion(cliente_id, direccion=None, tipo="envio", cp=None, municipio=None,
                      provincia=None, pais=None, id_empresa=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO clientes_direcciones (id_cliente, id_empresa, tipo, direccion, "
                        "cp, municipio, provincia, pais) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (cliente_id, id_empresa, tipo, direccion, cp, municipio, provincia, pais))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("agregar_direccion: %s", e)
        return None


def listar_direcciones(cliente_id, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes_direcciones WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY id", (cliente_id, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_direcciones: %s", e)
        return []


# ── Historial comercial ───────────────────────────────────────────────────────
def historial_comercial(cliente_id, id_empresa=None) -> dict:
    """Ventas + devoluciones + saldo del cliente (resumen 360º)."""
    id_empresa = id_empresa or empresa_actual_id()
    out = {"ventas": [], "devoluciones": [], "total_ventas": 0.0, "total_devoluciones": 0.0,
           "saldo": 0.0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, fecha, total, forma_pago FROM ventas WHERE cliente_id=%s "
                        "AND id_empresa=%s ORDER BY fecha DESC LIMIT 500", (cliente_id, id_empresa))
            out["ventas"] = [_fila(cur, r) for r in cur.fetchall()]
            out["total_ventas"] = round(sum(float(v["total"] or 0) for v in out["ventas"]), 2)
            cur.execute("SELECT d.id, d.fecha, d.total_reembolso FROM devoluciones d "
                        "JOIN ventas v ON v.id=d.venta_original_id WHERE v.cliente_id=%s "
                        "AND d.id_empresa=%s ORDER BY d.fecha DESC LIMIT 500", (cliente_id, id_empresa))
            out["devoluciones"] = [_fila(cur, r) for r in cur.fetchall()]
            out["total_devoluciones"] = round(
                sum(float(d["total_reembolso"] or 0) for d in out["devoluciones"]), 2)
        out["saldo"] = round(out["total_ventas"] - out["total_devoluciones"], 2)
        return out
    except Exception as e:
        logger.error("historial_comercial(%s): %s", cliente_id, e)
        return out
