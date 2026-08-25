# src/db/pedidos.py
import json

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion


def _tenant_actual():
    """(id_empresa, id_tienda) ACTIVOS para aislar pedidos por tienda (3b.2)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return empresa_actual_id(), tienda_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID, None


# ============================================================
# BLOQUE CONSULTA DE PEDIDOS
# ============================================================

def obtener_pedido_por_pale(pale_codigo):
    emp, tnd = _tenant_actual()
    filtros = ["pale_codigo=%s", "procesado=0", "id_empresa=%s"]
    params = [pale_codigo, emp]
    if tnd is not None:
        filtros.append("id_tienda=%s"); params.append(tnd)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, pale_codigo, items, procesado, fecha "
            "FROM pedidos WHERE " + " AND ".join(filtros) + " ORDER BY id DESC",
            tuple(params),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "pale_codigo": row[1],
        "items": json.loads(row[2]),
        "procesado": row[3],
        "fecha": row[4],
    }


# ============================================================
# BLOQUE CREACIÓN DE PEDIDOS
# ============================================================

def crear_pedido(pale_codigo, items):
    emp, tnd = _tenant_actual()
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pedidos (pale_codigo, items, id_empresa, id_tienda) "
            "VALUES (%s,%s,%s,%s)",
            (pale_codigo, json.dumps(items), emp, tnd),
        )
        conn.commit()


# ============================================================
# BLOQUE ACTUALIZACIÓN DE PEDIDOS
# ============================================================

def marcar_procesado(id_pedido):
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE pedidos SET procesado=1 WHERE id=%s", (id_pedido,))
        conn.commit()


def listar_pedidos(id_empresa=None, id_tienda=None, procesado=None, limite=100) -> list[dict]:
    """Lista de pedidos de recepción de palets (más recientes primero). `id_empresa` SIEMPRE debe
    indicarse explícitamente en contextos multiempresa (p. ej. la REST API); si se omite, cae en el
    tenant de la sesión de escritorio activa (igual que el resto del módulo)."""
    if id_empresa is None:
        id_empresa, tienda_activa = _tenant_actual()
        if id_tienda is None:
            id_tienda = tienda_activa
    filtros = ["id_empresa=%s"]
    params = [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s")
        params.append(id_tienda)
    if procesado is not None:
        filtros.append("procesado=%s")
        params.append(1 if procesado else 0)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, pale_codigo, items, procesado, fecha, id_tienda FROM pedidos WHERE "
            + " AND ".join(filtros) + " ORDER BY id DESC LIMIT %s",
            (*params, int(limite)),
        )
        rows = cursor.fetchall()
    out = []
    for row in rows:
        try:
            items = json.loads(row[2]) if row[2] else []
        except Exception:
            items = []
        out.append({"id": row[0], "pale_codigo": row[1], "items": items,
                    "procesado": bool(row[3]), "fecha": row[4], "id_tienda": row[5]})
    return out
