"""
Capa de servicio de VENTA ONLINE desde TPV (F2) — neutra respecto a plataforma.

Aísla la lógica de pedidos online para poder conectar más adelante Shopify,
WooCommerce, PrestaShop o una web propia SIN tocar la UI ni la BD: el adaptador
de plataforma se registra con `set_proveedor(fn)` y recibe el pedido ya creado.
Por defecto no hace nada externo (modo 'interno').

Multitienda: cada pedido se registra bajo la empresa/tienda ACTIVAS y el
trabajador en sesión (cuenta para la tienda y el trabajador aunque el envío lo
haga el almacén central). Ver [[project_centro_documental]] / [[project_multitenant]].
"""

import logging
import uuid

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("online_orders")

# Estados del ciclo de vida de un pedido online.
ESTADOS = ("PENDIENTE", "PAGADO", "PREPARANDO", "ENVIADO", "ENTREGADO", "CANCELADO")

# Adaptador de plataforma (Shopify/Woo/Presta/web). fn(pedido_dict) -> ref|None.
_proveedor = None


def set_proveedor(fn):
    """Registra el adaptador de e-commerce (futuras integraciones)."""
    global _proveedor
    _proveedor = fn


def _ctx():
    """(id_empresa, id_tienda, id_usuario, nombre) del contexto/sesión activos."""
    id_empresa, id_tienda = EMPRESA_DEFAULT_ID, None
    id_usuario, nombre = None, None
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        id_empresa = empresa_actual_id()
        id_tienda = tienda_actual_id()
    except Exception:
        pass
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        id_usuario = u.get("id")
        nombre = u.get("nombre") or u.get("usuario")
    except Exception:
        pass
    return id_empresa, id_tienda, id_usuario, nombre


# ── Disponibilidad multi-origen ──────────────────────────────────────────────
def consultar_disponibilidad(codigo: str) -> dict:
    """Disponibilidad de un artículo: stock en la tienda activa, en el almacén
    central, en otras tiendas y online. Permite decidir si se genera el pedido."""
    out = {"codigo": codigo, "nombre": "", "precio": 0.0, "tienda": 0, "central": 0,
           "otras_tiendas": [], "online": 0}
    try:
        _emp, _tnd, _u, _n = _ctx()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT nombre, COALESCE(precio,0), COALESCE(Stock_tienda,0), COALESCE(Stock_central,0) "
                "FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, _emp))
            r = cur.fetchone()
            if r:
                if isinstance(r, dict):
                    vals = list(r.values())
                    out["nombre"] = vals[0] or ""
                    out["precio"] = float(vals[1] or 0)
                    out["tienda"] = int(vals[2] or 0)
                    out["central"] = int(vals[3] or 0)
                else:
                    out["nombre"] = r[0] or ""
                    out["precio"] = float(r[1] or 0)
                    out["tienda"] = int(r[2] or 0)
                    out["central"] = int(r[3] or 0)
            # Stock en OTRAS tiendas (tabla stock_tienda, excluyendo la activa).
            cur.execute(
                "SELECT st.id_tienda, COALESCE(t.nombre, CONCAT('TND-', st.id_tienda)), st.stock "
                "FROM stock_tienda st LEFT JOIN tiendas t ON t.id=st.id_tienda "
                "WHERE st.codigo_articulo=%s AND st.id_empresa=%s "
                + ("AND st.id_tienda<>%s " if _tnd is not None else "")
                + "AND st.stock>0 ORDER BY st.id_tienda",
                ((codigo, _emp, _tnd) if _tnd is not None else (codigo, _emp)))
            for f in cur.fetchall():
                tid = f[0] if not isinstance(f, dict) else f["id_tienda"]
                nom = f[1] if not isinstance(f, dict) else list(f.values())[1]
                stk = f[2] if not isinstance(f, dict) else list(f.values())[2]
                out["otras_tiendas"].append({"id_tienda": tid, "nombre": nom, "stock": int(stk or 0)})
    except Exception as e:
        logger.error("consultar_disponibilidad(%s): %s", codigo, e)
    return out


# ── Crear / listar / actualizar pedidos online ───────────────────────────────
def crear_pedido_online(cliente: dict, lineas: list[dict], direccion_envio: str = "",
                        observaciones: str = "", plataforma: str = "interno",
                        referencia_externa: str | None = None,
                        estado: str = "PENDIENTE") -> str | None:
    """Crea un pedido online bajo la empresa/tienda/trabajador ACTIVOS.

    - cliente: {id?, nombre, telefono?, email?}
    - lineas: [{codigo, nombre, cantidad, precio, subtotal?, origen_stock?}]
    Devuelve el id_pedido o None.
    """
    if not lineas:
        return None
    if estado not in ESTADOS:
        estado = "PENDIENTE"
    id_empresa, id_tienda, id_usuario, trabajador = _ctx()
    cliente = cliente or {}
    total = 0.0
    norm = []
    for l in lineas:
        cant = float(l.get("cantidad", 1) or 1)
        precio = float(l.get("precio", 0) or 0)
        sub = float(l.get("subtotal") if l.get("subtotal") is not None else cant * precio)
        total += sub
        norm.append((l.get("codigo"), l.get("nombre"), int(cant), precio, sub,
                     l.get("origen_stock") or "central"))
    id_pedido = str(uuid.uuid4())
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pedidos_online "
                "(id_pedido, id_empresa, id_tienda, id_usuario, trabajador, cliente_id, "
                " cliente_nombre, cliente_telefono, cliente_email, direccion_envio, total, "
                " estado, plataforma, referencia_externa, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_pedido, id_empresa, id_tienda, id_usuario, trabajador,
                 cliente.get("id"), cliente.get("nombre"), cliente.get("telefono"),
                 cliente.get("email"), direccion_envio, round(total, 2), estado,
                 plataforma, referencia_externa, observaciones))
            for codigo, nombre, cant, precio, sub, origen in norm:
                cur.execute(
                    "INSERT INTO pedidos_online_items "
                    "(id_pedido, codigo_articulo, nombre, cantidad, precio_unitario, subtotal, origen_stock) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (id_pedido, codigo, nombre, cant, precio, sub, origen))
            conn.commit()
    except Exception as e:
        logger.error("crear_pedido_online: %s", e)
        return None

    # Sincronización con la plataforma de e-commerce. No bloquea la creación local.
    try:
        ped = obtener_pedido(id_pedido)
        if _proveedor is not None:          # override manual (set_proveedor)
            ref = _proveedor(ped)
        else:                                # adaptador multiplataforma configurado
            from src.services.tpv.ecommerce import adaptador_actual
            ref = adaptador_actual().crear_pedido(ped)
        if ref:
            cambiar_referencia_externa(id_pedido, ref)
    except Exception as e:
        logger.warning("Sincronización e-commerce falló (pedido %s): %s", id_pedido, e)
    # Si el pedido nace ya PAGADO, emite el justificante de pago.
    if estado == "PAGADO":
        _on_pagado(id_pedido)
    return id_pedido


def listar_pedidos_online(id_empresa=None, id_tienda="auto", estado=None,
                          texto=None, limite=1000) -> list[dict]:
    """Lista pedidos online de la empresa/tienda ACTIVAS (aislamiento por tienda)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        if id_empresa is None:
            id_empresa = empresa_actual_id()
        if id_tienda == "auto":
            id_tienda = tienda_actual_id()
    except Exception:
        if id_tienda == "auto":
            id_tienda = None
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if texto:
        filtros.append("(cliente_nombre LIKE %s OR cliente_telefono LIKE %s "
                       "OR cliente_email LIKE %s OR id_pedido LIKE %s "
                       "OR referencia_externa LIKE %s)")
        params += [f"%{texto}%"] * 5
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pedidos_online WHERE " + " AND ".join(filtros) +
                " ORDER BY fecha DESC, id_pedido DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            filas = cur.fetchall()
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in filas]
    except Exception as e:
        logger.error("listar_pedidos_online: %s", e)
        return []


# Estados que cuentan como venta confirmada para las analíticas (todo lo que no
# está pendiente de cobro ni cancelado).
ESTADOS_FACTURABLES = ("PAGADO", "PREPARANDO", "ENVIADO", "ENTREGADO")


def facturacion_por_dia(fecha_desde=None, fecha_hasta=None,
                        id_empresa=None, id_tienda="auto") -> dict:
    """Facturación de pedidos online por día (clave 'YYYY-MM-DD' -> total) de la
    empresa/tienda ACTIVAS. Solo cuenta estados facturables. Integra el canal
    online en las analíticas de Ventas."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        if id_empresa is None:
            id_empresa = empresa_actual_id()
        if id_tienda == "auto":
            id_tienda = tienda_actual_id()
    except Exception:
        if id_tienda == "auto":
            id_tienda = None
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    filtros.append("estado IN (%s)" % ",".join(["%s"] * len(ESTADOS_FACTURABLES)))
    params += list(ESTADOS_FACTURABLES)
    if fecha_desde:
        filtros.append("DATE(fecha) >= %s"); params.append(str(fecha_desde)[:10])
    if fecha_hasta:
        filtros.append("DATE(fecha) <= %s"); params.append(str(fecha_hasta)[:10])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE(fecha) AS d, COALESCE(SUM(total),0) AS t "
                "FROM pedidos_online WHERE " + " AND ".join(filtros) + " GROUP BY DATE(fecha)",
                tuple(params))
            out = {}
            for r in cur.fetchall():
                d = r["d"] if isinstance(r, dict) else r[0]
                t = r["t"] if isinstance(r, dict) else r[1]
                if d is not None:
                    out[str(d)[:10]] = float(t or 0)
            return out
    except Exception as e:
        logger.error("facturacion_por_dia: %s", e)
        return {}


def obtener_pedido(id_pedido: str) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM pedidos_online WHERE id_pedido=%s", (id_pedido,))
            r = cur.fetchone()
            if not r:
                return None
            if not isinstance(r, dict):
                r = dict(zip([d[0] for d in cur.description], r))
            cur.execute(
                "SELECT codigo_articulo, nombre, cantidad, precio_unitario, subtotal, origen_stock "
                "FROM pedidos_online_items WHERE id_pedido=%s", (id_pedido,))
            items = []
            for f in cur.fetchall():
                if isinstance(f, dict):
                    items.append(f)
                else:
                    items.append({"codigo_articulo": f[0], "nombre": f[1], "cantidad": f[2],
                                  "precio_unitario": f[3], "subtotal": f[4], "origen_stock": f[5]})
            r["items"] = items
            return r
    except Exception as e:
        logger.error("obtener_pedido(%s): %s", id_pedido, e)
        return None


def cambiar_estado(id_pedido: str, nuevo_estado: str) -> bool:
    if nuevo_estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET estado=%s WHERE id_pedido=%s",
                        (nuevo_estado, id_pedido))
            conn.commit()
        if nuevo_estado == "PAGADO":
            _on_pagado(id_pedido)
        elif nuevo_estado == "CANCELADO":
            _reponer_stock_pedido(id_pedido)
        return True
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def _generar_pdf_pedido(id_pedido: str, titulo: str, prefijo: str,
                        es_justificante: bool = False) -> str | None:
    """Genera un PDF (comprobante o justificante) de un pedido online y lo
    registra en el centro documental (tipo 'pedido'). Devuelve la ruta o None."""
    import os
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.warning("reportlab no disponible para %s: %s", prefijo, e)
        return None
    try:
        from src.db.empresa import info_documento
        emp = info_documento()
    except Exception:
        emp = {}
    try:
        from src.utils.recursos import ruta_datos
        carpeta = ruta_datos("pedidos")
    except Exception:
        carpeta = os.path.join("documentos", "pedidos")
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"{prefijo}_{id_pedido}.pdf")
    try:
        c = canvas.Canvas(ruta, pagesize=A4)
        W, H = A4
        y = H - 24 * mm
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20 * mm, y, (emp.get("nombre") or "SMART MANAGER")[:60])
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        for ln in (emp.get("direccion_completa"), f"CIF: {emp.get('cif','')}",
                   emp.get("telefono"), emp.get("email")):
            if ln:
                c.drawString(20 * mm, y, str(ln)[:90]); y -= 4.5 * mm
        y -= 4 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, y, titulo); y -= 8 * mm
        c.setFont("Helvetica", 9)
        fecha = str(pedido.get("fecha") or "")[:19]
        cabecera = [f"Pedido: {id_pedido}", f"Fecha: {fecha}",
                    f"Estado: {pedido.get('estado','')}",
                    f"Plataforma: {pedido.get('plataforma','')}",
                    f"Trabajador: {pedido.get('trabajador') or '-'}",
                    f"Cliente: {pedido.get('cliente_nombre') or '-'}",
                    f"Tel.: {pedido.get('cliente_telefono') or '-'}   "
                    f"Email: {pedido.get('cliente_email') or '-'}",
                    f"Envío: {pedido.get('direccion_envio') or '-'}"]
        if es_justificante:
            ref = pedido.get("referencia_externa")
            cabecera.append("PAGO CONFIRMADO" + (f"   Ref.: {ref}" if ref else ""))
        for ln in cabecera:
            c.drawString(20 * mm, y, ln[:100]); y -= 5 * mm
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "Artículo"); c.drawString(120 * mm, y, "Cant.")
        c.drawString(140 * mm, y, "Precio"); c.drawString(170 * mm, y, "Subtotal")
        y -= 2 * mm; c.line(20 * mm, y, 190 * mm, y); y -= 5 * mm
        c.setFont("Helvetica", 9)
        for it in pedido.get("items", []):
            c.drawString(20 * mm, y, str(it.get("nombre") or it.get("codigo_articulo") or "")[:60])
            c.drawRightString(132 * mm, y, str(it.get("cantidad", 0)))
            c.drawRightString(162 * mm, y, f"{float(it.get('precio_unitario',0)):.2f}")
            c.drawRightString(190 * mm, y, f"{float(it.get('subtotal',0)):.2f}")
            y -= 5 * mm
        y -= 2 * mm; c.line(120 * mm, y, 190 * mm, y); y -= 6 * mm
        c.setFont("Helvetica-Bold", 11)
        etiqueta_total = "TOTAL PAGADO: " if es_justificante else "TOTAL: "
        c.drawRightString(190 * mm, y, f"{etiqueta_total}{float(pedido.get('total',0)):.2f}")
        c.setFont("Helvetica", 7)
        c.drawString(20 * mm, 15 * mm, f"Trazabilidad: {id_pedido}")
        c.showPage(); c.save()
    except Exception as e:
        logger.error("_generar_pdf_pedido(%s, %s): %s", id_pedido, prefijo, e)
        return None
    # Registrar en el centro documental.
    try:
        from src.db import documentos as _docreg
        _docreg.registrar_documento(
            ruta, tipo="pedido", referencia=id_pedido,
            cliente=pedido.get("cliente_nombre"), trabajador=pedido.get("trabajador"),
            importe=pedido.get("total"), estado=pedido.get("estado"))
    except Exception as e:
        logger.debug("No se pudo registrar %s: %s", prefijo, e)
    return ruta


def generar_comprobante(id_pedido: str) -> str | None:
    """Comprobante PDF del pedido online (centro documental, tipo 'pedido')."""
    return _generar_pdf_pedido(
        id_pedido, "COMPROBANTE DE PEDIDO ONLINE", "comprobante_pedido")


def generar_justificante_pago(id_pedido: str) -> str | None:
    """Justificante de pago PDF del pedido online. Se genera automáticamente al
    pasar el pedido a PAGADO (centro documental, tipo 'pedido')."""
    return _generar_pdf_pedido(
        id_pedido, "JUSTIFICANTE DE PAGO", "justificante_pago",
        es_justificante=True)


def _marcar_stock_descontado(id_pedido: str, valor: int) -> None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET stock_descontado=%s WHERE id_pedido=%s",
                        (valor, id_pedido))
            conn.commit()
    except Exception as e:
        logger.debug("marcar_stock_descontado(%s): %s", id_pedido, e)


def _descontar_stock_pedido(id_pedido: str) -> None:
    """Descuenta del inventario las líneas de un pedido online (idempotente).

    Usa el descuento canónico con bloqueo de fila (central→tienda). Solo actúa
    una vez por pedido (flag ``stock_descontado``). No bloquea el cambio de
    estado: si una línea no tiene stock, se registra y se continúa."""
    pedido = obtener_pedido(id_pedido)
    if not pedido or int(pedido.get("stock_descontado") or 0):
        return
    try:
        from src.db.conexion import descontar_stock
    except Exception as e:
        logger.warning("descontar_stock no disponible (%s): %s", id_pedido, e)
        return
    detalle = []
    for it in pedido.get("items", []):
        codigo = it.get("codigo_articulo")
        cant = int(it.get("cantidad", 0) or 0)
        if not codigo or cant <= 0:
            continue
        try:
            ok, _t, _ti = descontar_stock(codigo, cant)
        except Exception as e:
            ok = False
            logger.warning("descontar_stock(%s, %s): %s", codigo, cant, e)
        detalle.append(f"{codigo}x{cant}{'' if ok else '(sin stock)'}")
        if not ok:
            logger.warning("Pedido online %s: sin stock para %s x%s", id_pedido, codigo, cant)
    _marcar_stock_descontado(id_pedido, 1)
    _auditar_stock(id_pedido, "DESCUENTO_STOCK_ONLINE", detalle)


def _reponer_stock_pedido(id_pedido: str) -> None:
    """Repone el stock de un pedido online cancelado (solo si se había descontado)."""
    pedido = obtener_pedido(id_pedido)
    if not pedido or not int(pedido.get("stock_descontado") or 0):
        return
    detalle = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for it in pedido.get("items", []):
                codigo = it.get("codigo_articulo")
                cant = int(it.get("cantidad", 0) or 0)
                if not codigo or cant <= 0:
                    continue
                cur.execute(
                    "UPDATE articulos SET Stock_total = COALESCE(Stock_total,0) + %s "
                    "WHERE codigo = %s", (cant, codigo))
                detalle.append(f"{codigo}x{cant}")
            conn.commit()
    except Exception as e:
        logger.warning("reponer_stock_pedido(%s): %s", id_pedido, e)
        return
    _marcar_stock_descontado(id_pedido, 0)
    _auditar_stock(id_pedido, "REPOSICION_STOCK_ONLINE", detalle)


def _auditar_stock(id_pedido: str, accion: str, detalle: list) -> None:
    try:
        from src.db.conexion import log_auditoria
        usuario = _ctx()[3] or "sistema"
        log_auditoria(usuario, accion, "pedidos_online",
                      f"{id_pedido}: {', '.join(detalle) or '-'}")
    except Exception as e:
        logger.debug("auditar_stock(%s): %s", id_pedido, e)


def _on_pagado(id_pedido: str) -> None:
    """Acciones automáticas al confirmarse el pago de un pedido online."""
    try:
        generar_justificante_pago(id_pedido)
    except Exception as e:
        logger.warning("No se pudo generar el justificante de pago (%s): %s",
                       id_pedido, e)
    try:
        _descontar_stock_pedido(id_pedido)
    except Exception as e:
        logger.warning("No se pudo descontar el stock del pedido (%s): %s",
                       id_pedido, e)


def cambiar_referencia_externa(id_pedido: str, referencia: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET referencia_externa=%s WHERE id_pedido=%s",
                        (referencia, id_pedido))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cambiar_referencia_externa(%s): %s", id_pedido, e)
        return False
