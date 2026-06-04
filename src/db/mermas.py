import logging
from datetime import datetime

from src.db.conexion import obtener_conexion

# ============================================================
# BLOQUE CONSULTA DE MERMAS
# ============================================================


def obtener_mermas(mes=None):
    """Recupera mermas, opcionalmente filtradas por mes (YYYY-MM)."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            query = "SELECT id, codigo, cantidad, motivo, fecha FROM mermas"
            if mes:
                query += f" WHERE fecha LIKE '{mes}%'"
            query += " ORDER BY fecha DESC"
            cursor.execute(query)
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error al obtener mermas: {e}")
        return []


# ============================================================
# BLOQUE REGISTRO Y MODIFICACIÓN DE MERMAS
# ============================================================


def registrar_merma(codigo, cantidad, motivo):
    """Registra una merma en la base de datos."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO mermas (codigo, cantidad, motivo, fecha) VALUES (%s,%s,%s,%s)",
                (codigo, cantidad, motivo, fecha),
            )
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error al registrar merma: {e}")
        return False


def modificar_merma(id_merma, nueva_cantidad):
    """Ajusta la cantidad de una merma existente."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mermas SET cantidad=%s WHERE id=%s", (nueva_cantidad, id_merma)
            )
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error al modificar merma: {e}")
        return False


# ============================================================
# BLOQUE ELIMINACIÓN DE MERMAS
# ============================================================


def eliminar_merma(id_merma):
    """Elimina una merma del registro."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mermas WHERE id=%s", (id_merma,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error eliminando merma: {e}")
        return False
