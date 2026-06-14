import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion


def _tenant_actual():
    """(id_empresa, id_tienda) ACTIVOS para aislar mermas por tienda (3b.3)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return empresa_actual_id(), tienda_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID, None


# ============================================================
# BLOQUE CONSULTA DE MERMAS
# ============================================================


def obtener_mermas(mes=None):
    """Recupera mermas de la tienda activa, opcionalmente filtradas por mes (YYYY-MM)."""
    try:
        emp, tnd = _tenant_actual()
        filtros, params = ["id_empresa=%s"], [emp]
        if tnd is not None:
            filtros.append("id_tienda=%s"); params.append(tnd)
        if mes:
            filtros.append("fecha LIKE %s"); params.append(f"{mes}%")
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, codigo, cantidad, motivo, fecha FROM mermas WHERE "
                + " AND ".join(filtros) + " ORDER BY fecha DESC",
                tuple(params))
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
            emp, tnd = _tenant_actual()
            cursor.execute(
                "INSERT INTO mermas (codigo, cantidad, motivo, fecha, id_empresa, id_tienda) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (codigo, cantidad, motivo, fecha, emp, tnd),
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
