"""
Kárdex unificado de movimientos de stock (INV.1).

Registro central de TODOS los movimientos en `movimientos_stock` y consultas
reutilizables para el visor e informes. `registrar_movimiento` es **best-effort**: nunca
lanza excepción ni participa en la transacción de stock/venta/devolución (se invoca tras
el commit), de modo que el TPV/devoluciones/stock siguen funcionando exactamente igual.
Multiempresa por `id_empresa` (+ id_tienda). Tipos soportados (compatibles con los
previos): ENTRADA_COMPRA, ENTRADA_PALE, ENTRADA_TRASPASO, TRASPASO, MERMA, SALIDA_VENTA,
DEVOLUCION, AJUSTE.
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, ensure_schema,
                             obtener_conexion)

logger = logging.getLogger("inventario.kardex")

TIPOS = (
    "ENTRADA_COMPRA", "ENTRADA_PALE", "ENTRADA_TRASPASO", "TRASPASO", "MERMA",
    "SALIDA_VENTA", "DEVOLUCION", "AJUSTE", "DEVOLUCION_PROVEEDOR",
    # MRP / Fabricación (BLOQUE 3) — alta de producto terminado y consumo de componentes.
    "ENTRADA_PRODUCCION", "SALIDA_PRODUCCION",
)
# Signo orientativo (+ entra, − sale) — informativo, no altera el dato almacenado.
ENTRADAS = {"ENTRADA_COMPRA", "ENTRADA_PALE", "ENTRADA_TRASPASO", "DEVOLUCION", "ENTRADA_PRODUCCION"}
SALIDAS = {"SALIDA_VENTA", "MERMA", "SALIDA_PRODUCCION"}


def _tenant():
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return empresa_actual_id(), tienda_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID, None


def existe_movimiento(codigo, tipo, id_documento, id_empresa=None) -> bool:
    """True si ya hay un movimiento de ese tipo para (codigo, id_documento) — idempotencia."""
    if id_documento is None or not codigo:
        return False
    try:
        if id_empresa is None:
            id_empresa, _ = _tenant()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM movimientos_stock WHERE id_empresa=%s AND codigo_articulo=%s "
                        "AND tipo_movimiento=%s AND id_documento=%s LIMIT 1",
                        (id_empresa, str(codigo), tipo, str(id_documento)))
            return cur.fetchone() is not None
    except Exception:
        return False


def registrar_movimiento(codigo, tipo, cantidad, *, id_documento=None, id_pale=None,
                         origen=None, destino=None, usuario=None, observaciones=None,
                         id_empresa=None, id_tienda=None, stock_anterior=None,
                         stock_nuevo=None, id_almacen_origen=None, id_almacen_destino=None,
                         idempotente=False) -> bool:
    """Inserta un movimiento en el kárdex. Best-effort: devuelve False sin propagar
    errores. No usar dentro de la transacción de stock (invocar tras el commit).
    id_almacen_origen/destino (INV.4) localizan el movimiento por almacén. Si `idempotente`
    y ya existe un movimiento de ese tipo para (codigo, id_documento), no duplica (H1)."""
    try:
        if not codigo or tipo not in TIPOS:
            return False
        if id_empresa is None or id_tienda is None:
            _e, _t = _tenant()
            id_empresa = id_empresa or _e
            id_tienda = id_tienda if id_tienda is not None else _t
        if idempotente and id_documento is not None and existe_movimiento(
                codigo, tipo, id_documento, id_empresa):
            return True
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO movimientos_stock
                    (codigo_articulo, tipo_movimiento, cantidad, id_documento, id_pale,
                     origen, destino, usuario, observaciones, id_empresa, id_tienda,
                     stock_anterior, stock_nuevo, id_almacen_origen, id_almacen_destino)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (str(codigo), tipo, int(cantidad or 0),
                 str(id_documento) if id_documento is not None else None,
                 str(id_pale) if id_pale is not None else None,
                 origen, destino, str(usuario) if usuario is not None else None,
                 observaciones, id_empresa, id_tienda, stock_anterior, stock_nuevo,
                 id_almacen_origen, id_almacen_destino),
            )
            conn.commit()
        return True
    except Exception as e:  # nunca debe afectar a la operación original
        logger.warning("kardex registrar_movimiento(%s,%s): %s", codigo, tipo, e)
        return False


# ── Consultas (visor + informes) ──────────────────────────────────────────────
def listar_movimientos(id_empresa=None, codigo=None, tipo=None, desde=None, hasta=None,
                       id_tienda=None, referencia=None, usuario=None, id_almacen=None,
                       limite=1000) -> list:
    """Consulta filtrable del kárdex (multiempresa). Orden cronológico descendente."""
    try:
        ensure_schema()
        cond, params = [], []
        if id_empresa:
            cond.append("id_empresa=%s"); params.append(id_empresa)
        if codigo:
            cond.append("codigo_articulo=%s"); params.append(str(codigo))
        if tipo:
            cond.append("tipo_movimiento=%s"); params.append(tipo)
        if id_tienda is not None:
            cond.append("id_tienda=%s"); params.append(id_tienda)
        if id_almacen is not None:
            cond.append("(id_almacen_origen=%s OR id_almacen_destino=%s)")
            params += [id_almacen, id_almacen]
        if referencia:
            cond.append("(id_documento=%s OR id_pale=%s)"); params += [str(referencia)] * 2
        if usuario:
            cond.append("usuario=%s"); params.append(str(usuario))
        if desde:
            cond.append("fecha_movimiento >= %s"); params.append(desde)
        if hasta:
            cond.append("fecha_movimiento <= %s"); params.append(str(hasta) + " 23:59:59"
                                                                   if len(str(hasta)) == 10 else hasta)
        where = (" WHERE " + " AND ".join(cond)) if cond else ""
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM movimientos_stock{where} "
                f"ORDER BY fecha_movimiento DESC, id DESC LIMIT %s",
                (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_movimientos: %s", e)
        return []


def historial_articulo(codigo, id_empresa=None, limite=1000) -> list:
    """Historial cronológico completo de un artículo (ascendente)."""
    movs = listar_movimientos(id_empresa=id_empresa, codigo=codigo, limite=limite)
    return list(reversed(movs))


def movimientos_por_periodo(desde, hasta, id_empresa=None, **kw) -> list:
    return listar_movimientos(id_empresa=id_empresa, desde=desde, hasta=hasta, **kw)


def movimientos_por_tienda(id_tienda, id_empresa=None, **kw) -> list:
    return listar_movimientos(id_empresa=id_empresa, id_tienda=id_tienda, **kw)


def movimientos_por_usuario(usuario, id_empresa=None, **kw) -> list:
    return listar_movimientos(id_empresa=id_empresa, usuario=usuario, **kw)
