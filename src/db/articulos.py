from src.db.conexion import obtener_conexion

# ============================================================
# BLOQUE CONSULTA DE ARTÍCULOS
# ============================================================

def obtener_articulos():
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo, nombre, Stock_total, precio, capacidad_lineal, bloqueado, "
            "ultima_recepcion, siguiente_recepcion, ubicacion_tienda FROM articulos"
        )
        return cursor.fetchall()


# ============================================================
# BLOQUE ACTUALIZACIÓN DE ARTÍCULOS
# ============================================================

def actualizar_precio(codigo, nuevo_precio):
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE articulos SET precio=%s WHERE codigo=%s", (nuevo_precio, codigo)
        )
        conn.commit()
    return True
