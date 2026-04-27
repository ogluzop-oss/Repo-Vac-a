import sqlite3
from datetime import datetime
from src.db.conexion import obtener_conexion


def registrar_venta(codigo: str, cantidad_vendida: int) -> bool:
    """
    Registra una venta en la base de datos y actualiza únicamente el stock de tienda (Stock_tienda).

    Parámetros:
        codigo (str): Código único del artículo vendido.
        cantidad_vendida (int): Unidades vendidas del artículo.

    Retorna:
        bool: True si la venta fue registrada correctamente, False si hubo un error.
    """
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        # Verificar si el artículo existe y obtener Stock_tienda
        cursor.execute("SELECT Stock_tienda FROM articulos WHERE codigo = ?", (codigo,))
        resultado = cursor.fetchone()

        if not resultado:
            print(f"⚠️ El artículo con código '{codigo}' no existe en la base de datos.")
            return False

        stock_tienda_actual = resultado[0]

        # Comprobar si hay suficiente stock en tienda
        if stock_tienda_actual < cantidad_vendida:
            print(
                f"❌ Stock insuficiente para el artículo '{codigo}'. "
                f"Stock actual: {stock_tienda_actual}, solicitado: {cantidad_vendida}."
            )
            return False

        # Registrar la venta en la tabla 'ventas'
        fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO ventas (codigo, cantidad, fecha)
            VALUES (?, ?, ?)
        """,
            (codigo, cantidad_vendida, fecha_venta),
        )

        # Actualizar solo el stock de tienda (Stock_tienda)
        nuevo_stock_tienda = stock_tienda_actual - cantidad_vendida
        cursor.execute(
            """
            UPDATE articulos
            SET Stock_tienda = ?
            WHERE codigo = ?
        """,
            (nuevo_stock_tienda, codigo),
        )

        conn.commit()
        print(
            f"✅ Venta registrada correctamente: {cantidad_vendida} unidades de '{codigo}'. "
            f"Nuevo stock de tienda: {nuevo_stock_tienda}"
        )

        return True

    except sqlite3.Error as e:
        print(f"❌ Error al registrar la venta: {e}")
        return False

    finally:
        conn.close()
