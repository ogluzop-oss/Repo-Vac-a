"""
PCD · Carrito del storefront público (Motor de Alta Conversión e-Commerce — Drawer Cart).

Carrito INCREMENTAL identificado solo por `token_sesion` (cookie opaca de navegador, sin sesión de
empresa — comprador anónimo hasta que paga). Mismo patrón exacto ya validado en producción para el
carrito B2B (`services.compras.b2b_carrito`), adaptado al comprador público. Reutiliza:
  · `services.catalogo` para precio/nombre/imagen/disponibilidad de cada línea (nunca se guarda un
    precio "de memoria" al añadir — se relee del catálogo en cada operación).
  · `comercio_digital.comercial.cotizar` para el total con promociones + cupón + envío por zona
    (el carrito NUNCA calcula descuentos/envío por su cuenta).
No mueve stock, no crea el pedido — eso es `tpv.online_orders_service.crear_pedido_online`, al
confirmar el checkout.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("cd.carrito_storefront")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _tocar_actividad(token_sesion, id_empresa, email=None) -> None:
    """Registra la última vez que el carrito cambió de contenido (ver mismo razonamiento que
    `b2b_carrito._tocar_actividad`: `creado_en` por sí solo no basta, una retirada de línea no
    quedaría reflejada). `email`, si se da, se persiste SIEMPRE (nunca se borra uno ya capturado
    por una llamada posterior que no lo trae) — captura temprana de leads, pedido explícito."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if email:
                cur.execute(
                    "INSERT INTO cd_carrito_actividad (token_sesion, id_empresa, email, actualizado_en) "
                    "VALUES (%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE id_empresa=VALUES(id_empresa), "
                    "email=VALUES(email), actualizado_en=NOW()", (token_sesion, id_empresa, email))
            else:
                cur.execute(
                    "INSERT INTO cd_carrito_actividad (token_sesion, id_empresa, actualizado_en) "
                    "VALUES (%s,%s,NOW()) ON DUPLICATE KEY UPDATE id_empresa=VALUES(id_empresa), "
                    "actualizado_en=NOW()", (token_sesion, id_empresa))
            conn.commit()
    except Exception as e:
        logger.debug("_tocar_actividad(%s): %s", token_sesion, e)


def anadir(token_sesion, id_empresa, *, id_producto=None, codigo=None, cantidad=1) -> dict:
    """Añade un artículo (o incrementa su cantidad si ya estaba) — relee precio/nombre/imagen/
    disponibilidad del catálogo público SIEMPRE, nunca confía en un precio recibido del cliente.

    Acepta `id_producto` (el id del catálogo, ÚNICO identificador que la ficha pública expone para
    el producto BASE — `catalogo.serializar` nunca da `codigo_articulo` en vista pública, a
    propósito) o `codigo` directo (usado para una VARIANTE concreta, cuyo `codigo_articulo` SÍ
    viaja ya en `variantes[].codigo_articulo` del JSON público — ver `catalogo.listar_variantes`).
    Al menos uno de los dos es obligatorio."""
    cantidad = int(cantidad or 1)
    if cantidad < 1:
        return {"ok": False, "error": "cantidad_debe_ser_mayor_o_igual_a_1"}
    if not id_producto and not codigo:
        return {"ok": False, "error": "falta_identificador_de_producto"}
    from src.services import catalogo as cat_svc
    if codigo:
        prod = cat_svc.producto(codigo_articulo=codigo, interno=False, id_empresa=id_empresa)
        codigo_real = codigo
    else:
        prod = cat_svc.producto(id_producto=id_producto, interno=False, id_empresa=id_empresa)
        codigo_real = None
        if prod:
            from src.db import catalogo as cat_db
            fila = cat_db.obtener_producto(id_producto=id_producto, id_empresa=id_empresa)
            codigo_real = (fila or {}).get("codigo_articulo")
    if not prod or not codigo_real:
        return {"ok": False, "error": "producto_no_disponible"}
    if not prod.get("disponible"):
        return {"ok": False, "error": "sin_stock"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_carrito_lineas (token_sesion, id_empresa, codigo, nombre, imagen, "
                "cantidad, precio_unitario) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE cantidad=cantidad+VALUES(cantidad), "
                "nombre=VALUES(nombre), imagen=VALUES(imagen), precio_unitario=VALUES(precio_unitario)",
                (token_sesion, id_empresa, codigo_real, prod.get("nombre"), prod.get("imagen"),
                 cantidad, float(prod.get("precio") or 0)))
            conn.commit()
        _tocar_actividad(token_sesion, id_empresa)
        return {"ok": True}
    except Exception as e:
        logger.error("anadir(%s,%s): %s", token_sesion, codigo_real, e)
        return {"ok": False, "error": "error_interno"}


def listar(token_sesion) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cd_carrito_lineas WHERE token_sesion=%s ORDER BY creado_en",
                        (token_sesion,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar(%s): %s", token_sesion, e)
        return []


def actualizar_cantidad(token_sesion, id_linea, cantidad) -> dict:
    """`cantidad <= 0` quita la línea (mismo criterio que cualquier carrito de e-commerce: bajar a
    0 con el selector de cantidad equivale a eliminarla)."""
    cantidad = int(cantidad or 0)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM cd_carrito_lineas WHERE id=%s AND token_sesion=%s",
                        (id_linea, token_sesion))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "linea_no_encontrada"}
            id_empresa = row[0] if not isinstance(row, dict) else row["id_empresa"]
            if cantidad <= 0:
                cur.execute("DELETE FROM cd_carrito_lineas WHERE id=%s AND token_sesion=%s",
                            (id_linea, token_sesion))
            else:
                cur.execute("UPDATE cd_carrito_lineas SET cantidad=%s WHERE id=%s AND token_sesion=%s",
                            (cantidad, id_linea, token_sesion))
            conn.commit()
        _tocar_actividad(token_sesion, id_empresa)
        return {"ok": True}
    except Exception as e:
        logger.error("actualizar_cantidad(%s,%s): %s", token_sesion, id_linea, e)
        return {"ok": False, "error": "error_interno"}


def quitar_linea(token_sesion, id_linea) -> bool:
    return actualizar_cantidad(token_sesion, id_linea, 0).get("ok", False)


def vaciar(token_sesion) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_carrito_lineas WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
        # Carrito tramitado/vaciado -> deja de estar "abandonado" (mismo criterio que b2b_carrito).
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM cd_carrito_actividad WHERE token_sesion=%s", (token_sesion,))
                cur.execute("UPDATE cd_carrito_abandono SET resuelto=1 WHERE token_sesion=%s AND resuelto=0",
                            (token_sesion,))
                conn.commit()
        except Exception as e:
            logger.debug("vaciar/limpieza_abandono(%s): %s", token_sesion, e)
        return True
    except Exception as e:
        logger.error("vaciar(%s): %s", token_sesion, e)
        return False


def capturar_email(token_sesion, id_empresa, email) -> bool:
    """Captura temprana de leads (pedido explícito): se llama en cuanto el comprador escribe su
    email en el checkout, ANTES de completar el pago — para que el carrito sea recuperable aunque
    abandone justo ahí."""
    email = (email or "").strip()
    if not email or "@" not in email:
        return False
    _tocar_actividad(token_sesion, id_empresa, email=email)
    return True


def email_de(token_sesion) -> str | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email FROM cd_carrito_actividad WHERE token_sesion=%s", (token_sesion,))
            r = cur.fetchone()
            if not r:
                return None
            return (r[0] if not isinstance(r, dict) else r["email"]) or None
    except Exception as e:
        logger.debug("email_de(%s): %s", token_sesion, e)
        return None


def resumen(token_sesion, id_empresa, *, cupon=None, pais_destino="ES") -> dict:
    """Vista COMPLETA del carrito para el Drawer Cart / checkout: líneas + cotización real
    (promociones + cupón + envío por zona, vía `comercial.cotizar` — nunca recalculado a mano
    aquí) + datos listos para la barra de progreso de envío gratis."""
    lineas_db = listar(token_sesion)
    lineas_cotizar = [{"codigo": l["codigo"], "cantidad": int(l["cantidad"]),
                       "precio_unitario": float(l["precio_unitario"])} for l in lineas_db]
    if not lineas_cotizar:
        return {"lineas": [], "n_articulos": 0, "subtotal": 0.0, "descuento_total": 0.0,
                "envio": {"coste": 0.0, "gratis": False, "umbral_envio_gratis": None,
                         "falta_para_envio_gratis": 0.0},
                "total": 0.0, "cupon": None}
    from src.services.comercio_digital.comercial import cotizar
    q = cotizar(lineas_cotizar, cupon=cupon, pais_destino=pais_destino, id_empresa=id_empresa)
    por_codigo = {d["codigo"]: d for d in q["lineas"]}
    lineas_vista = []
    for l in lineas_db:
        d = por_codigo.get(l["codigo"], {})
        lineas_vista.append({
            "id": l["id"], "codigo": l["codigo"], "nombre": l.get("nombre") or l["codigo"],
            "imagen": l.get("imagen"), "cantidad": int(l["cantidad"]),
            "precio_unitario": float(l["precio_unitario"]), "subtotal": d.get("neto", float(l["precio_unitario"]) * int(l["cantidad"])),
        })
    n_articulos = sum(l["cantidad"] for l in lineas_vista)
    return {"lineas": lineas_vista, "n_articulos": n_articulos, "subtotal": q["subtotal"],
            "descuento_total": q["descuento_total"], "envio": q["envio"], "total": q["total"],
            "cupon": q["cupon"], "moneda": q["moneda"]}
