from src.db.conexion import obtener_conexion


# ============================================================
# BLOQUE CONSULTA DE ETIQUETAS
# ============================================================

def obtener_etiquetas_pendientes():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo, nombre, precio_actual, nuevo_precio FROM etiquetas")
    resultados = cursor.fetchall()
    etiquetas = []
    for r in resultados:
        etiquetas.append(
            {
                "codigo": r[0],
                "nombre": r[1],
                "precio_actual": r[2],
                "nuevo_precio": r[3],
            }
        )
    conn.close()
    return etiquetas


# ============================================================
# BLOQUE REGISTRO DE ETIQUETAS
# ============================================================

def agregar_etiqueta_pendiente(codigo):
    conn = obtener_conexion()
    cursor = conn.cursor()
    # Obtener datos del artículo
    cursor.execute("SELECT nombre, precio FROM articulos WHERE codigo=?", (codigo,))
    resultado = cursor.fetchone()
    if resultado:
        nombre, precio = resultado
        cursor.execute(
            "INSERT INTO etiquetas (codigo, nombre, precio_actual, nuevo_precio) VALUES (?,?,?,?)",
            (codigo, nombre, precio, precio),
        )
    conn.commit()
    conn.close()


# ============================================================
# BLOQUE LIMPIEZA DE ETIQUETAS
# ============================================================

def refrescar_precios():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM etiquetas")
    conn.commit()
    conn.close()
