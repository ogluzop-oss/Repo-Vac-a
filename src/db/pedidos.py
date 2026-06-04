# src/db/pedidos.py
import json

from src.db.conexion import obtener_conexion

# ============================================================
# BLOQUE CONSULTA DE PEDIDOS
# ============================================================

def obtener_pedido_por_pale(pale_codigo):
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, pale_codigo, items, procesado, fecha "
            "FROM pedidos WHERE pale_codigo=%s AND procesado=0 ORDER BY id DESC",
            (pale_codigo,),
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
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pedidos (pale_codigo, items) VALUES (%s,%s)",
            (pale_codigo, json.dumps(items)),
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
