"""
Expediciones / Distribución mayorista B2B (R8·it3) — FUNCIÓN BASE (no una edición): ORQUESTA la cadena
que YA existe (nombre `expediciones` para no chocar con el paquete `services/distribucion`, que es el motor
de sincronización de datos entre terminales):

    pedido de cliente  →  preparación (picking WMS)  →  expedición  →  salida de stock OFICIAL

Reutiliza íntegramente los motores existentes (N7 — cero lógica de pedido/stock/documento paralela):
  · `db/ventas_comercial`  — pedido de cliente + conversión a venta (dispara la salida de stock oficial).
  · `services/inventario/almacen_pro` + `picking_ruta` — picking y ruta óptima de picking.
  · `services/logistica/logistica_pro` — expediciones y transportistas.
  · `services/comercio_digital/comercial` — tarifa mayorista (`cd_precios_lista`, lista="mayorista").

Multi-tenant por `id_empresa` (la conversión a venta usa el contexto de empresa activo, como el TPV).
"""

import logging

logger = logging.getLogger("expediciones")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def precio_mayorista(codigo, id_empresa=None):
    """Precio de la tarifa 'mayorista' para el artículo, o None si no hay (→ se usa el precio base)."""
    try:
        from src.services.comercio_digital.comercial import precio_de_lista
        return precio_de_lista(codigo, lista="mayorista", id_empresa=_emp(id_empresa))
    except Exception:
        return None


# ── Pedido mayorista ──────────────────────────────────────────────────────────
def crear_pedido(id_cliente, lineas, observaciones=None, id_empresa=None, usuario=None) -> int | None:
    """Crea un pedido de cliente reutilizando `ventas_comercial.crear_pedido_cliente`. Por cada línea, si
    no se aporta precio se resuelve la TARIFA MAYORISTA (o el precio base). `lineas=[{codigo, cantidad,
    precio?}]`."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
    except Exception as e:
        logger.error("crear_pedido import: %s", e)
        return None
    lns = []
    for l in (lineas or []):
        cod = (l.get("codigo") or l.get("codigo_articulo") or "").strip()
        if not cod:
            continue
        precio = l.get("precio") if l.get("precio") is not None else l.get("precio_unitario")
        if precio in (None, "", 0):
            precio = precio_mayorista(cod, emp) or _precio_base(cod, emp) or 0
        lns.append({"codigo": cod, "descripcion": l.get("descripcion"),
                    "cantidad": int(l.get("cantidad") or 0), "precio_unitario": round(float(precio or 0), 2)})
    if not lns:
        return None
    try:
        return VC.crear_pedido_cliente(id_cliente=id_cliente, lineas=lns, observaciones=observaciones,
                                       usuario=usuario, id_empresa=emp)
    except Exception as e:
        logger.error("crear_pedido: %s", e)
        return None


def _precio_base(codigo, id_empresa):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT precio FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if r:
                return float((r[0] if not isinstance(r, dict) else r.get("precio")) or 0)
    except Exception:
        pass
    return 0.0


# ── Preparación (picking WMS) ─────────────────────────────────────────────────
def preparar(id_pedido, responsable=None, id_empresa=None) -> int | None:
    """Crea un PICKING para el pedido (reutiliza `almacen_pro.crear_picking`, origen='pedido')."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
        from src.services.inventario import almacen_pro as AP
    except Exception as e:
        logger.error("preparar import: %s", e)
        return None
    ped = VC.obtener_pedido_cliente(id_pedido, id_empresa=emp)
    if not ped:
        return None
    lineas = [{"codigo": l.get("codigo_articulo"), "cantidad": int(l.get("cantidad") or 0)}
              for l in ped.get("lineas", []) if l.get("codigo_articulo")]
    if not lineas:
        return None
    try:
        return AP.crear_picking(lineas, referencia=f"pedido:{id_pedido}", origen="pedido",
                                id_documento=id_pedido, responsable=responsable, id_empresa=emp)
    except Exception as e:
        logger.error("preparar: %s", e)
        return None


def ruta_optima(id_picking, id_empresa=None):
    """Ruta óptima de picking (serpentín) del picking (reutiliza `picking_ruta.ruta_picking`)."""
    try:
        from src.services.inventario.picking_ruta import ruta_picking
        return ruta_picking(id_picking, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("ruta_optima: %s", e)
        return ([], {})


# ── Expedición (salida de stock OFICIAL + registro de envío) ──────────────────
def expedir(id_pedido, id_transportista=None, direccion=None, id_empresa=None, usuario=None) -> dict:
    """Expide el pedido: convierte a VENTA (salida de stock OFICIAL vía `convertir_a_venta`, protegida
    contra doble conversión) y registra la EXPEDICIÓN (`logistica_pro.crear_expedicion`)."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
    except Exception as e:
        return {"ok": False, "error": str(e)}
    venta_id = VC.convertir_a_venta(id_pedido, usuario=usuario, id_empresa=emp)
    if not venta_id:
        return {"ok": False, "error": "El pedido no se pudo expedir (inexistente, ya convertido o cancelado)."}
    exp_id = None
    try:
        from src.services.logistica import logistica_pro as LP
        exp_id = LP.crear_expedicion(referencia=f"pedido:{id_pedido}", id_transportista=id_transportista,
                                     origen="pedido", id_documento=id_pedido, direccion=direccion, id_empresa=emp)
    except Exception as e:
        logger.error("expedir/expedicion: %s", e)
    return {"ok": True, "venta_id": venta_id, "expedicion_id": exp_id}


# ── Listados / transportistas (passthrough) ───────────────────────────────────
def listar_pedidos(id_empresa=None, estado=None) -> list:
    try:
        from src.db import ventas_comercial as VC
        return VC.listar("pedidos_cliente", id_empresa=_emp(id_empresa), estado=estado)
    except Exception as e:
        logger.error("listar_pedidos: %s", e)
        return []


def listar_transportistas(id_empresa=None) -> list:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.transportistas(id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("listar_transportistas: %s", e)
        return []


def crear_transportista(nombre, contacto=None, telefono=None, id_empresa=None) -> int | None:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.crear_transportista(nombre, contacto=contacto, telefono=telefono, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("crear_transportista: %s", e)
        return None
