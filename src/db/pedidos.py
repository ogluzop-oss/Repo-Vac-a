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
