from src.db.conexion import obtener_conexion

# ============================================================
# BLOQUE CONSULTA DE ETIQUETAS
# ============================================================

def obtener_etiquetas_pendientes():
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, nombre, precio_actual, nuevo_precio FROM etiquetas")
        return [
            {"codigo": r[0], "nombre": r[1], "precio_actual": r[2], "nuevo_precio": r[3]}
            for r in cursor.fetchall()
        ]


# ============================================================
# BLOQUE REGISTRO DE ETIQUETAS
# ============================================================

def agregar_etiqueta_pendiente(codigo):
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, precio FROM articulos WHERE codigo=%s", (codigo,))
        resultado = cursor.fetchone()
        if resultado:
            nombre, precio = resultado
            cursor.execute(
                "INSERT INTO etiquetas (codigo, nombre, precio_actual, nuevo_precio) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "precio_actual=VALUES(precio_actual), nuevo_precio=VALUES(nuevo_precio)",
                (codigo, nombre, precio, precio),
            )
            conn.commit()


# ============================================================
# BLOQUE LIMPIEZA DE ETIQUETAS
# ============================================================

def refrescar_precios():
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM etiquetas")
        conn.commit()
