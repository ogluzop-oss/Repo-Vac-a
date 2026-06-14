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

    # Hook de plataforma (futuras integraciones). No bloquea la creación local.
    if _proveedor is not None:
        try:
            ref = _proveedor(obtener_pedido(id_pedido))
            if ref:
                cambiar_referencia_externa(id_pedido, ref)
        except Exception as e:
            logger.warning("Adaptador de plataforma falló (pedido %s): %s", id_pedido, e)
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
        return True
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def generar_comprobante(id_pedido: str) -> str | None:
    """Genera el comprobante PDF del pedido online y lo registra en el centro
    documental (tipo 'pedido'). Devuelve la ruta o None."""
    import os
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.warning("reportlab no disponible para el comprobante: %s", e)
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
    ruta = os.path.join(carpeta, f"comprobante_pedido_{id_pedido}.pdf")
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
        c.drawString(20 * mm, y, "COMPROBANTE DE PEDIDO ONLINE"); y -= 8 * mm
        c.setFont("Helvetica", 9)
        fecha = str(pedido.get("fecha") or "")[:19]
        for ln in (f"Pedido: {id_pedido}", f"Fecha: {fecha}",
                   f"Estado: {pedido.get('estado','')}",
                   f"Plataforma: {pedido.get('plataforma','')}",
                   f"Trabajador: {pedido.get('trabajador') or '-'}",
                   f"Cliente: {pedido.get('cliente_nombre') or '-'}",
                   f"Tel.: {pedido.get('cliente_telefono') or '-'}   "
                   f"Email: {pedido.get('cliente_email') or '-'}",
                   f"Envío: {pedido.get('direccion_envio') or '-'}"):
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
        c.drawRightString(190 * mm, y, f"TOTAL: {float(pedido.get('total',0)):.2f}")
        c.setFont("Helvetica", 7)
        c.drawString(20 * mm, 15 * mm, f"Trazabilidad: {id_pedido}")
        c.showPage(); c.save()
    except Exception as e:
        logger.error("generar_comprobante(%s): %s", id_pedido, e)
        return None
    # Registrar en el centro documental.
    try:
        from src.db import documentos as _docreg
        _docreg.registrar_documento(
            ruta, tipo="pedido", referencia=id_pedido,
            cliente=pedido.get("cliente_nombre"), trabajador=pedido.get("trabajador"),
            importe=pedido.get("total"), estado=pedido.get("estado"))
    except Exception as e:
        logger.debug("No se pudo registrar el comprobante: %s", e)
    return ruta


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
