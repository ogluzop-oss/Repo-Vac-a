# src/db/pedidos.py
from src.db.conexion import obtener_conexion
import json


# ============================================================
# BLOQUE CONSULTA DE PEDIDOS
# ============================================================

def obtener_pedido_por_pale(pale_codigo):
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM pedidos WHERE pale_codigo = ? AND procesado = 0 ORDER BY id DESC",
        (pale_codigo,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["items"] = json.loads(data["items"])
    return data


# ============================================================
# BLOQUE CREACIÓN DE PEDIDOS
# ============================================================

def crear_pedido(pale_codigo, items):
    conn = obtener_conexion()
    c = conn.cursor()
    items_json = json.dumps(items)
    c.execute(
        "INSERT INTO pedidos (pale_codigo, items) VALUES (?,?)",
        (pale_codigo, items_json),
    )
    conn.commit()
    conn.close()


# ============================================================
# BLOQUE ACTUALIZACIÓN DE PEDIDOS
# ============================================================

def marcar_procesado(id_pedido):
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("UPDATE pedidos SET procesado = 1 WHERE id = ?", (id_pedido,))
    conn.commit()
    conn.close()
