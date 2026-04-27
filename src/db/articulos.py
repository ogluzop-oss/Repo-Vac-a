from src.db.conexion import obtener_conexion


# ============================================================
# BLOQUE CONSULTA DE ARTÍCULOS
# ============================================================

def obtener_articulos():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT codigo, nombre, cantidad, precio, capacidad_lineal, bloqueado, ultima_recepcion, siguiente_recepcion, ubicacion FROM articulos"
    )
    resultados = cursor.fetchall()
    conn.close()
    return resultados


# ============================================================
# BLOQUE ACTUALIZACIÓN DE ARTÍCULOS
# ============================================================

def actualizar_precio(codigo, nuevo_precio):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE articulos SET precio=? WHERE codigo=?", (nuevo_precio, codigo)
    )
    conn.commit()
    conn.close()
    return True
