"""
CAL-E — Trazabilidad de calidad. NO crea trazabilidad paralela: reutiliza lotes/movimientos_stock
(db.lotes) y agrega la dimension calidad (inspecciones/NC) + OF de origen. Soporte opcional de
numero de serie via el campo `lote` (un lote de 1 unidad = serie).
"""

import logging
import re
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.trazabilidad")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.calidad.identidad_calidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        return id_empresa or empresa_actual_id()


def _filas(cur):
    return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))) for r in cur.fetchall()]


def _proveedor_de_pedido(cur, id_pedido, eid):
    """Resuelve nombre de proveedor + nº de pedido a partir de un id_pedido de compras_pedidos."""
    try:
        cur.execute("SELECT id_proveedor, numero FROM compras_pedidos WHERE id_pedido=%s "
                    "AND id_empresa=%s", (id_pedido, eid))
        ped = cur.fetchone()
        if not ped:
            return None
        id_prov, numero = (ped["id_proveedor"], ped["numero"]) if isinstance(ped, dict) else (ped[0], ped[1])
        nombre_prov = None
        if id_prov:
            cur.execute("SELECT COALESCE(nombre_comercial, razon_social) FROM proveedores "
                        "WHERE id_proveedor=%s", (id_prov,))
            r = cur.fetchone()
            nombre_prov = (list(r.values())[0] if isinstance(r, dict) else r[0]) if r else None
        return {"id_pedido": id_pedido, "numero_pedido": numero, "id_proveedor": id_prov,
                "proveedor": nombre_prov}
    except Exception as e:
        logger.debug("_proveedor_de_pedido(%s): %s", id_pedido, e)
        return None


def _proveedor_de_pedido_b2b(cur, id_tx, eid):
    """Resuelve proveedor de origen + pedido a partir de un id_tx de `transaccion_comercial`
    (Smart Suppliers B2B — `suministradores`, NO `proveedores`: es un ecosistema de proveedor
    distinto del módulo clásico de Compras). Solo lectura directa, mismo criterio que
    `_proveedor_de_pedido` (sin importar `services.compras.b2b_pedidos` para no acoplar capas)."""
    try:
        cur.execute("SELECT id_suministrador FROM transaccion_comercial WHERE id_tx=%s "
                    "AND id_empresa=%s", (id_tx, eid))
        tx = cur.fetchone()
        if not tx:
            return None
        id_sum = tx["id_suministrador"] if isinstance(tx, dict) else tx[0]
        nombre_prov = None
        if id_sum:
            cur.execute("SELECT razon_social FROM suministradores WHERE id=%s", (id_sum,))
            r = cur.fetchone()
            nombre_prov = (list(r.values())[0] if isinstance(r, dict) else r[0]) if r else None
        return {"id_tx": id_tx, "id_suministrador": id_sum, "proveedor": nombre_prov}
    except Exception as e:
        logger.debug("_proveedor_de_pedido_b2b(%s): %s", id_tx, e)
        return None


def _origen_compra(cur, lote_row, eid):
    """Resuelve proveedor de origen + referencia de pedido a partir de `lotes.origen`/
    `id_documento`. Dos ecosistemas de proveedor distintos comparten `origen='compra'`/
    `'compra_b2b'` con formatos de `id_documento` distintos (no son duplicados, son módulos
    diferentes — ver CLAUDE.md):
    - `db/compras.py::recibir` (módulo clásico de Compras, `proveedores`/`compras_pedidos`)
      escribe `id_documento='PC{id_pedido}-R{rid}'`.
    - `services/compras/b2b_pedidos.py::recibir_mercancia` (Smart Suppliers B2B,
      `suministradores`/`transaccion_comercial`) escribe `id_documento='B2B-{id_tx}'`.
    Solo lectura: no crea ninguna tabla ni columna nueva."""
    origen = (lote_row.get("origen") or "").strip().lower()
    id_documento = lote_row.get("id_documento") or ""
    if origen not in ("compra", "compra_b2b"):
        return None
    m = re.match(r"^PC(\d+)-R\d+$", str(id_documento))
    if m:
        info = _proveedor_de_pedido(cur, int(m.group(1)), eid) or {}
        info["origen"] = origen
        info["id_documento"] = id_documento
        return info
    m2 = re.match(r"^B2B-(.+)$", str(id_documento))
    if m2:
        info = _proveedor_de_pedido_b2b(cur, m2.group(1), eid) or {}
        info["origen"] = origen
        info["id_documento"] = id_documento
        return info
    return {"origen": origen, "id_documento": id_documento, "proveedor": None, "id_pedido": None}


def _distribucion_ventas(cur, id_lote):
    """Ventas a las que se distribuyó este lote (venta_items.id_lote, migr. 0039). `ventas` no
    guarda un cliente identificado por venta (solo empleado/caja) — se devuelve lo que el
    esquema realmente tiene, sin inventar un nombre de cliente que no existe."""
    try:
        cur.execute(
            "SELECT vi.venta_id, vi.codigo_articulo, vi.cantidad, v.fecha, v.empleado, v.numero_caja "
            "FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id "
            "WHERE vi.id_lote = %s ORDER BY v.fecha DESC LIMIT 500", (id_lote,))
        return _filas(cur)
    except Exception as e:
        logger.debug("_distribucion_ventas(%s): %s", id_lote, e)
        return []


def trazabilidad_lote(id_lote, *, id_empresa=None) -> dict:
    """Une la trazabilidad de stock (kardex) del lote con su calidad (inspecciones + NC).

    Aditivo (INV.3 track&trace, Punto 3): además de movimientos/inspecciones/NC/OF de origen, ya
    resuelve proveedor de origen + pedido B2B (`lotes.origen`/`id_documento`), ubicación actual
    (`lotes.id_almacen`), estado de bloqueo (`lotes.estado`) y distribución a ventas
    (`venta_items.id_lote`). No cambia la forma de los datos ya existentes."""
    eid = _emp(id_empresa)
    out = {"movimientos": [], "inspecciones": [], "no_conformidades": [], "of_origen": None,
           "lote": None, "bloqueado": False, "ubicacion": None, "origen_compra": None,
           "distribucion_ventas": []}
    try:
        from src.db import lotes
        out["movimientos"] = lotes.trazabilidad_lote(id_lote, id_empresa=eid)
    except Exception as e:
        logger.debug("trazabilidad stock: %s", e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM inspecciones WHERE id_empresa=%s AND id_lote=%s", (eid, id_lote))
            out["inspecciones"] = _filas(cur)
            cur.execute("SELECT * FROM no_conformidades WHERE id_empresa=%s AND id_lote=%s", (eid, id_lote))
            out["no_conformidades"] = _filas(cur)
            # OF de origen: lote producido por una OF cuyo lote_destino coincide.
            cur.execute("SELECT o.id, o.codigo FROM ordenes_fabricacion o JOIN lotes l ON l.lote=o.lote_destino "
                        "AND l.id_empresa=o.id_empresa WHERE l.id=%s LIMIT 1", (id_lote,))
            r = cur.fetchone()
            out["of_origen"] = (r if isinstance(r, dict) else {"id": r[0], "codigo": r[1]}) if r else None

            cur.execute("SELECT * FROM lotes WHERE id=%s AND id_empresa=%s", (id_lote, eid))
            lote_row = _filas(cur)
            lote_row = lote_row[0] if lote_row else None
            if lote_row:
                out["lote"] = lote_row
                out["bloqueado"] = str(lote_row.get("estado") or "").strip().lower() == "bloqueado"
                out["ubicacion"] = lote_row.get("id_almacen")
                out["origen_compra"] = _origen_compra(cur, lote_row, eid)
            out["distribucion_ventas"] = _distribucion_ventas(cur, id_lote)
    except Exception as e:
        logger.debug("trazabilidad calidad: %s", e)
    return out


def trazabilidad_articulo(codigo, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    out = {"movimientos": [], "inspecciones": [], "no_conformidades": []}
    try:
        from src.db import lotes
        out["movimientos"] = lotes.trazabilidad_articulo(codigo, id_empresa=eid)
    except Exception:
        pass
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM inspecciones WHERE id_empresa=%s AND articulo=%s ORDER BY fecha DESC LIMIT 200",
                        (eid, codigo))
            out["inspecciones"] = _filas(cur)
            cur.execute("SELECT * FROM no_conformidades WHERE id_empresa=%s AND articulo=%s "
                        "ORDER BY fecha_apertura DESC LIMIT 200", (eid, codigo))
            out["no_conformidades"] = _filas(cur)
    except Exception as e:
        logger.debug("trazabilidad articulo calidad: %s", e)
    return out
