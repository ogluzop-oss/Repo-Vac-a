"""
Capa de datos de COMPRAS (E2) — pedidos, recepción, costes, facturas, informes.

Ciclo: proveedor → pedido → recepción (stock + movimientos) → costes → factura.
Multiempresa por `id_empresa`. Reutiliza `articulos`/`movimientos_stock` existentes
sin romper TPV/stock/catálogo. Operaciones que mueven stock son ATÓMICAS
(`transaccion()`).

Este módulo crece por subfases (E2.2 pedidos; E2.3 recepción; E2.4 costes;
E2.5 facturas; E2.6 informes).
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion, transaccion)

logger = logging.getLogger("compras_db")

ESTADOS_PEDIDO = ("BORRADOR", "ENVIADO", "PARCIAL", "RECIBIDO", "CANCELADO")
# Transiciones permitidas.
_TRANSICIONES = {
    "BORRADOR": {"ENVIADO", "CANCELADO"},
    "ENVIADO": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "PARCIAL": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "RECIBIDO": set(),
    "CANCELADO": set(),
}


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


# ── Pedidos de compra (E2.2) ─────────────────────────────────────────────────
def crear_pedido(id_proveedor=None, lineas=None, observaciones=None, usuario=None,
                 id_empresa=None) -> int | None:
    """Crea un pedido en BORRADOR con sus líneas. `lineas`: [{codigo, descripcion,
    cantidad, precio_unitario}]. Calcula subtotales y total."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_pedidos (id_empresa, id_proveedor, estado, "
                "observaciones, usuario) VALUES (%s,%s,'BORRADOR',%s,%s)",
                (id_empresa, id_proveedor, observaciones, usuario))
            pid = cur.lastrowid
            cur.execute("UPDATE compras_pedidos SET numero=%s WHERE id_pedido=%s",
                        (f"PC{pid:06d}", pid))
            total = _insertar_lineas(cur, pid, lineas)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, pid))
        return pid
    except Exception as e:
        logger.error("crear_pedido: %s", e)
        return None


def _insertar_lineas(cur, id_pedido, lineas) -> float:
    total = 0.0
    for ln in lineas:
        cant = int(ln.get("cantidad") or 0)
        precio = round(float(ln.get("precio_unitario") or 0), 2)
        subtotal = round(cant * precio, 2)
        total += subtotal
        cur.execute(
            "INSERT INTO compras_pedidos_lineas (id_pedido, codigo_articulo, descripcion, "
            "cantidad, precio_unitario, subtotal) VALUES (%s,%s,%s,%s,%s,%s)",
            (id_pedido, ln.get("codigo") or ln.get("codigo_articulo"),
             ln.get("descripcion"), cant, precio, subtotal))
    return round(total, 2)


def obtener_pedido(id_pedido, id_empresa=None) -> dict | None:
    """Cabecera + líneas del pedido."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE id_pedido=%s AND id_empresa=%s",
                        (id_pedido, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_pedidos_lineas WHERE id_pedido=%s ORDER BY id",
                        (id_pedido,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_pedido(%s): %s", id_pedido, e)
        return None


def listar_pedidos(id_empresa=None, estado=None, id_proveedor=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if id_proveedor:
        filtros.append("id_proveedor=%s"); params.append(id_proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE " + " AND ".join(filtros)
                        + " ORDER BY id_pedido DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_pedidos: %s", e)
        return []


def modificar_lineas(id_pedido, lineas, id_empresa=None) -> bool:
    """Reemplaza las líneas de un pedido (solo en BORRADOR) y recalcula el total."""
    id_empresa = _empresa(id_empresa)
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped or ped["estado"] != "BORRADOR":
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM compras_pedidos_lineas WHERE id_pedido=%s", (id_pedido,))
            total = _insertar_lineas(cur, id_pedido, lineas)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, id_pedido))
        return True
    except Exception as e:
        logger.error("modificar_lineas(%s): %s", id_pedido, e)
        return False


def cambiar_estado(id_pedido, nuevo_estado, id_empresa=None) -> bool:
    """Cambia el estado validando la transición permitida."""
    id_empresa = _empresa(id_empresa)
    if nuevo_estado not in ESTADOS_PEDIDO:
        return False
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped:
        return False
    if nuevo_estado != ped["estado"] and nuevo_estado not in _TRANSICIONES.get(ped["estado"], set()):
        logger.warning("Transición no permitida %s->%s (pedido %s)", ped["estado"], nuevo_estado, id_pedido)
        return False
    campos = "estado=%s"
    params = [nuevo_estado]
    if nuevo_estado == "ENVIADO":
        campos += ", fecha_envio=NOW()"
    if nuevo_estado == "RECIBIDO":
        campos += ", fecha_recepcion=NOW()"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE compras_pedidos SET {campos} WHERE id_pedido=%s AND id_empresa=%s",
                        (*params, id_pedido, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def enviar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "ENVIADO", id_empresa)


def cancelar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "CANCELADO", id_empresa)
