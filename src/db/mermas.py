from src.db.conexion import obtener_conexion
from datetime import datetime
import logging


# ============================================================
# BLOQUE CONSULTA DE MERMAS
# ============================================================

def obtener_mermas():
    """Recupera el histórico completo de mermas."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, codigo, cantidad, motivo, fecha FROM mermas")
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error al obtener mermas: {e}")
        return []


# ============================================================
# BLOQUE REGISTRO Y MODIFICACIÓN DE MERMAS
# ============================================================

def registrar_merma(codigo, cantidad, motivo):
    """Registra una merma y descuenta el stock del artículo."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO mermas (codigo, cantidad, motivo, fecha) VALUES (?,?,?,?)",
                (codigo, cantidad, motivo, fecha),
            )
            cursor.execute(
                "UPDATE articulos SET cantidad = cantidad - ? WHERE codigo=?",
                (cantidad, codigo),
            )
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error al registrar merma: {e}")
        return False


def modificar_merma(id_merma, nueva_cantidad):
    """Ajusta una merma existente y recalcula el stock del artículo."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT codigo, cantidad FROM mermas WHERE id=?", (id_merma,)
            )
            resultado = cursor.fetchone()
            if not resultado:
                return False

            codigo, cantidad_antigua = resultado
            diff = nueva_cantidad - cantidad_antigua

            cursor.execute(
                "UPDATE mermas SET cantidad=? WHERE id=?", (nueva_cantidad, id_merma)
            )
            cursor.execute(
                "UPDATE articulos SET cantidad = cantidad - ? WHERE codigo=?",
                (diff, codigo),
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
    """Elimina una merma del registro utilizando la conexión centralizada."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mermas WHERE id = ?", (id_merma,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error eliminando merma: {e}")
        return False
