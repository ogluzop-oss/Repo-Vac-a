import sqlite3
import logging
from datetime import datetime
from src.db.conexion import obtener_conexion

logger = logging.getLogger(__name__)


# ============================================================
# BLOQUE REGISTRO DE TRASPASOS
# ============================================================

def guardar_traspaso_db(datos: dict):
    """
    Registra el traspaso logístico y descuenta existencias:
    1. Resta de stock_total (Almacén de la tienda)
    2. Resta de stock_tienda (Lineal/Exposición)
    """
    conn = obtener_conexion()
    cursor = conn.cursor()

    try:
        query_cabecera = """
            INSERT INTO documentos_logisticos (
                origen, 
                fecha_envio, 
                observaciones, 
                estado, 
                fecha_creacion
            ) VALUES (?, ?, ?, 'SALIDA', ?)
        """
        fecha_creacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            query_cabecera,
            (
                datos["tienda_origen"],
                datos["fecha_entrega"],
                datos["observaciones"],
                fecha_creacion,
            ),
        )

        traspaso_id = cursor.lastrowid

        query_detalle = """
            INSERT INTO recepciones_items (traspaso_id, codigo_articulo, cantidad, pale)
            VALUES (?, ?, ?, ?)
        """

        query_update_stock = """
            UPDATE articulos 
            SET stock_total = stock_total - ?,
                stock_tienda = stock_tienda - ?
            WHERE codigo = ?
        """

        for item in datos["items"]:
            codigo = item["codigo"]
            cantidad = item["cantidad"]
            pale = item["pale"]

            cursor.execute(query_detalle, (traspaso_id, codigo, cantidad, pale))
            cursor.execute(query_update_stock, (cantidad, cantidad, codigo))

            if cursor.rowcount == 0:
                raise Exception(
                    f"Error crítico: El artículo {codigo} no existe en la base de datos."
                )

        conn.commit()
        logger.info(
            f"Traspaso ID {traspaso_id} procesado: stocks de almacén y lineal actualizados."
        )
        return True, traspaso_id

    except Exception as e:
        conn.rollback()
        logger.error(f"Error al procesar el traspaso en DB: {e}")
        return False, str(e)
    finally:
        conn.close()
