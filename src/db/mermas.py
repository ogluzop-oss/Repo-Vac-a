import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion, transaccion


def _tenant_actual():
    """(id_empresa, id_tienda) ACTIVOS para aislar mermas por tienda (3b.3).
    id_tienda se coacciona a ENTERO porque `mermas.id_tienda` es INT (el contexto
    puede ser un código alfanumérico como 'ALMC' → provocaría DataError 1366)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id_int
        return empresa_actual_id(), tienda_actual_id_int()
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


def obtener_mermas_pendientes():
    """Mermas de la tienda activa AÚN NO exportadas a Excel (exportada=0), con el
    nombre del artículo (JOIN articulos). Devuelve dicts: id, codigo, nombre, fecha."""
    try:
        emp, tnd = _tenant_actual()
        filtros, params = ["m.id_empresa=%s", "COALESCE(m.exportada,0)=0"], [emp]
        if tnd is not None:
            filtros.append("m.id_tienda=%s"); params.append(tnd)
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT m.id, m.codigo, COALESCE(a.nombre, m.codigo) AS nombre, m.fecha "
                "FROM mermas m LEFT JOIN articulos a ON a.codigo = m.codigo "
                "WHERE " + " AND ".join(filtros) + " ORDER BY m.fecha DESC",
                tuple(params))
            return [
                {"id": r[0], "codigo": r[1], "nombre": r[2], "fecha": r[3]}
                for r in cur.fetchall()
            ]
    except Exception as e:
        logging.error(f"Error al obtener mermas pendientes: {e}")
        return []


def marcar_mermas_exportadas(ids):
    """Marca como exportadas (exportada=1) las mermas indicadas. Idempotente."""
    ids = [int(i) for i in (ids or []) if i is not None]
    if not ids:
        return 0
    try:
        with transaccion() as conn:
            cur = conn.cursor()
            marcadores = ",".join(["%s"] * len(ids))
            cur.execute(
                f"UPDATE mermas SET exportada=1 WHERE id IN ({marcadores})", tuple(ids))
            return cur.rowcount
    except Exception as e:
        logging.error(f"Error al marcar mermas exportadas: {e}")
        return 0


# ============================================================
# BLOQUE REGISTRO Y MODIFICACIÓN DE MERMAS
# ============================================================


def registrar_merma(codigo, cantidad, motivo, columna_stock=None):
    """Registra una merma y, si se indica `columna_stock` ('Stock_tienda' o
    'Stock_total'), descuenta el stock EN LA MISMA TRANSACCIÓN (A2.3) → evita
    estados parciales (merma registrada sin descuento de stock, o viceversa)."""
    col = columna_stock if columna_stock in ("Stock_tienda", "Stock_total") else None
    try:
        with transaccion() as conn:
            cursor = conn.cursor()
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            emp, tnd = _tenant_actual()
            cursor.execute(
                "INSERT INTO mermas (codigo, cantidad, motivo, fecha, id_empresa, id_tienda) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (codigo, cantidad, motivo, fecha, emp, tnd),
            )
            if col:
                cursor.execute(
                    f"UPDATE articulos SET {col} = GREATEST(0, COALESCE({col},0) - %s) "
                    "WHERE codigo = %s", (cantidad, codigo))
            _registrar_kardex = bool(col)
        # INV.1: kárdex MERMA (best-effort, tras commit; solo si hubo descuento de stock).
        if _registrar_kardex:
            try:
                from src.db import kardex
                kardex.registrar_movimiento(
                    codigo, "MERMA", cantidad, origen="MERMA", id_empresa=emp,
                    id_tienda=tnd, observaciones=motivo)
            except Exception:
                pass
            # INV.3: consumo FEFO de lotes por merma (best-effort, no-op si no hay lotes).
            try:
                from src.db import lotes
                lotes.consumir_fefo(codigo, cantidad, tipo="MERMA", id_empresa=emp,
                                    id_tienda=tnd, observaciones=motivo)
            except Exception:
                pass
            # INV.4: sincroniza el ledger multialmacén si el artículo está gestionado.
            try:
                from src.db import stock_almacen as SA
                if SA.esta_gestionado(codigo, emp):
                    SA.reseed_articulo(codigo, emp)
            except Exception:
                pass
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("MERMA_REGISTRADA", id_empresa=emp, id_tienda=tnd, origen="mermas",
                         ref_entidad="merma", ref_id=codigo,
                         payload={"codigo": codigo, "cantidad": cantidad, "motivo": motivo})
        except Exception:
            pass
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
