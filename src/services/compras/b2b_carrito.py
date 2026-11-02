"""
Carrito de la Extranet de Empresa (Smart Suppliers · Fase B). Dos orígenes por línea: 'catalogo'
(añadida buscando en el catálogo B2B) o 'reposicion' (añadida desde "Desde reposición", enlazada a la
propuesta de `reabastecimiento.py` vía `id_reab_propuesta` para poder marcarla "Añadida" sin que
desaparezca de la lista de sugerencias hasta tramitar — requisito de negocio confirmado).
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_carrito")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _tocar_actividad(token_sesion) -> None:
    """Registra la última vez que el CONTENIDO del carrito cambió (añadir o quitar una línea) — ver
    `b2b_carrito_abandono.py` para por qué `creado_en` por sí solo no basta (una retirada de línea sin
    ningún añadido posterior no se reflejaría en `MAX(creado_en)`). Best-effort: si la tabla (migración
    0280) no existe todavía, no debe romper el flujo normal del carrito."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_carrito_actividad (token_sesion, actualizado_en) VALUES (%s, NOW()) "
                "ON DUPLICATE KEY UPDATE actualizado_en=NOW()", (token_sesion,))
            conn.commit()
    except Exception as e:
        logger.debug("_tocar_actividad(%s): %s", token_sesion, e)


def anadir(token_sesion, *, id_suministrador, codigo, nombre, unidad_medida, cantidad,
          precio_unitario, origen="catalogo", id_reab_propuesta=None) -> dict:
    if int(cantidad) < 1:
        return {"ok": False, "error": "cantidad_debe_ser_mayor_o_igual_a_1"}
    # Un proveedor por pedido: un carrito no puede mezclar artículos de proveedores distintos —
    # cada pedido real solo puede ir a UN proveedor (ver `b2b_pedidos.tramitar`).
    lineas_actuales = listar(token_sesion)
    if lineas_actuales and lineas_actuales[0]["id_suministrador"] != id_suministrador:
        return {"ok": False, "error": "proveedor_distinto",
                "mensaje": "Ya tienes artículos de otro proveedor en el carrito — tramita o vacía "
                          "el pedido actual antes de añadir artículos de un proveedor distinto."}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_carrito_lineas (token_sesion, id_suministrador, codigo, nombre, "
                "unidad_medida, cantidad, precio_unitario, origen, id_reab_propuesta) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (token_sesion, id_suministrador, codigo, nombre, unidad_medida, int(cantidad),
                 float(precio_unitario), origen, id_reab_propuesta))
            id_linea = cur.lastrowid
            conn.commit()
        if origen == "reposicion" and id_reab_propuesta:
            from src.db import reabastecimiento as R
            R.cambiar_estado_propuesta(id_reab_propuesta, "en_carrito")
        _tocar_actividad(token_sesion)
        return {"ok": True, "id_linea": id_linea}
    except Exception as e:
        logger.error("anadir(%s,%s): %s", token_sesion, codigo, e)
        return {"ok": False, "error": "error_interno"}


def listar(token_sesion) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_carrito_lineas WHERE token_sesion=%s ORDER BY creado_en",
                        (token_sesion,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar(%s): %s", token_sesion, e)
        return []


def quitar_linea(token_sesion, id_linea) -> bool:
    """Quita una línea. Si venía de 'Desde reposición', la propuesta vuelve a 'pendiente' (deja de
    estar "Añadida" en la lista de sugerencias)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT origen, id_reab_propuesta FROM b2b_carrito_lineas "
                        "WHERE id=%s AND token_sesion=%s", (id_linea, token_sesion))
            row = cur.fetchone()
            info = _fila(cur, row) if row else None
            cur.execute("DELETE FROM b2b_carrito_lineas WHERE id=%s AND token_sesion=%s",
                        (id_linea, token_sesion))
            ok = cur.rowcount > 0
            conn.commit()
        if ok and info and info.get("origen") == "reposicion" and info.get("id_reab_propuesta"):
            from src.db import reabastecimiento as R
            R.cambiar_estado_propuesta(info["id_reab_propuesta"], "pendiente")
        if ok:
            _tocar_actividad(token_sesion)
        return ok
    except Exception as e:
        logger.error("quitar_linea(%s,%s): %s", token_sesion, id_linea, e)
        return False


def vaciar(token_sesion) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM b2b_carrito_lineas WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
        # Un carrito vaciado (tramitado -> b2b_pedidos.tramitar, o vaciado manualmente) deja de estar
        # "abandonado": limpia la actividad y cierra cualquier registro de abandono abierto para este
        # token. Best-effort (migración 0280) — nunca debe impedir vaciar el carrito.
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM b2b_carrito_actividad WHERE token_sesion=%s", (token_sesion,))
                cur.execute("UPDATE b2b_carrito_abandono SET resuelto=1 WHERE token_sesion=%s AND resuelto=0",
                            (token_sesion,))
                conn.commit()
        except Exception as e:
            logger.debug("vaciar/limpieza_abandono(%s): %s", token_sesion, e)
        return True
    except Exception as e:
        logger.error("vaciar(%s): %s", token_sesion, e)
        return False


def reasignar_token(token_viejo, token_nuevo) -> bool:
    """Transfiere las líneas de un carrito al token de una sesión NUEVA del mismo usuario — usado por
    "Reanudar Pedido" (Portal Empresa) sobre un carrito ya marcado como abandonado.

    Por qué hace falta transferir en vez de simplemente enlazar al carrito "de siempre": el umbral de
    abandono por defecto es 2h, el MISMO valor que `b2b_sesion_empresa.MINUTOS_SESION` (120 min). Como
    las líneas de un carrito solo pueden añadirse mientras su sesión está viva, un carrito detectado
    como abandonado (última actividad > 2h) casi siempre cuelga de un `token_sesion` cuya sesión YA ha
    caducado — `resolver_sesion` la rechazaría. Esta función NO reconstruye el carrito (las filas de
    `b2b_carrito_lineas` son las mismas, con sus precios/cantidades originales); solo cambia la clave
    de sesión a la que están ligadas, para que vuelvan a ser visibles bajo la sesión activa actual."""
    if not token_viejo or not token_nuevo or token_viejo == token_nuevo:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_carrito_lineas SET token_sesion=%s WHERE token_sesion=%s",
                        (token_nuevo, token_viejo))
            ok = cur.rowcount > 0
            conn.commit()
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM b2b_carrito_actividad WHERE token_sesion=%s", (token_viejo,))
                cur.execute(
                    "INSERT INTO b2b_carrito_actividad (token_sesion, actualizado_en) VALUES (%s, NOW()) "
                    "ON DUPLICATE KEY UPDATE actualizado_en=NOW()", (token_nuevo,))
                conn.commit()
        except Exception as e:
            logger.debug("reasignar_token/actividad(%s->%s): %s", token_viejo, token_nuevo, e)
        return ok
    except Exception as e:
        logger.error("reasignar_token(%s->%s): %s", token_viejo, token_nuevo, e)
        return False


def total(token_sesion) -> float:
    return round(sum(float(x["cantidad"]) * float(x["precio_unitario"]) for x in listar(token_sesion)), 2)
