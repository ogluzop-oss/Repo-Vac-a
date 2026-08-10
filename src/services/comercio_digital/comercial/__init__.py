"""
PCD · Gestión Comercial (Etapa B · Fase B4).

Capa comercial que COTIZA una cesta aplicando precios de lista + promociones + cupones y ofrece
sugerencias de venta cruzada/ascendente. REUTILIZA los motores existentes (N7); no crea uno nuevo:
  · Promociones/packs/descuentos → `db.promociones.evaluar_articulo` (descuento_pct/importe_fijo/2x1/
    pack/regalo/nxm/segunda_unidad).
  · Cupones → `db.fidelizacion.validar_cupon` / `redimir_cupon`.
  · Precios base → catálogo/artículo; NUEVO: listas de precios (`cd_precios_lista`).
  · Variantes (up-sell) → `comercio_digital.catalogo`.

Es composición/cálculo comercial (no mueve stock, no cobra, no crea la Transacción). El resultado
alimenta a la Transacción Comercial (núcleo omnicanal) en el checkout. Multiempresa.
"""

from __future__ import annotations

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.comercial")

FASE = "B4"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
# ── Listas de precios (pieza nueva) ───────────────────────────────────────────
def fijar_precio(lista, referencia, precio, *, ambito="articulo", moneda="EUR", canal=None,
                 segmento=None, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_precios_lista (id_empresa, lista, referencia, ambito, canal, segmento, "
                "moneda, precio) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE precio=VALUES(precio), ambito=VALUES(ambito), "
                "canal=VALUES(canal), segmento=VALUES(segmento), activo=1, ts_actualizado=NOW()",
                (emp, lista, str(referencia), ambito, canal, segmento, moneda, float(precio)))
            conn.commit()
            return True
    except Exception as e:
        logger.error("fijar_precio(%s/%s): %s", lista, referencia, e)
        return False


def precio_de_lista(referencia, *, lista=None, moneda="EUR", id_empresa=None):
    """Precio de una referencia en una lista/moneda, o None si no existe (→ se usa el precio base)."""
    if not lista:
        return None
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT precio FROM cd_precios_lista WHERE id_empresa=%s AND lista=%s AND "
                        "referencia=%s AND moneda=%s AND activo=1",
                        (emp, lista, str(referencia), moneda))
            r = cur.fetchone()
            if not r:
                return None
            return float(list(r.values())[0] if isinstance(r, dict) else r[0])
    except Exception as e:
        logger.error("precio_de_lista(%s): %s", referencia, e)
        return None


# ── Cotización comercial unificada (reutiliza promociones + cupones) ──────────
def cotizar(lineas, *, cliente_id=None, segmento=None, id_tienda=None, cupon=None, lista=None,
            moneda="EUR", id_empresa=None) -> dict:
    """Cotiza una cesta: precio de lista (o base) → mejor promoción por línea (db.promociones) →
    cupón sobre el total (db.fidelizacion). Devuelve el desglose. NO redime el cupón (eso es del
    checkout) ni crea la Transacción."""
    emp = _emp(id_empresa)
    from src.db import promociones as promo
    detalle, subtotal, desc_promos = [], 0.0, 0.0
    for l in (lineas or []):
        codigo = l.get("codigo") or l.get("codigo_articulo")
        cant = int(l.get("cantidad", 1) or 1)
        base = precio_de_lista(codigo, lista=lista, moneda=moneda, id_empresa=emp)
        if base is None:
            base = float(l.get("precio_unitario", l.get("precio", 0)) or 0)
        ev = promo.evaluar_articulo(codigo, base, cant, categoria=l.get("categoria"),
                                    cliente_id=cliente_id, segmento=segmento, id_tienda=id_tienda,
                                    id_empresa=emp)
        bruto = round(base * cant, 2)
        subtotal += bruto
        desc_promos += float(ev.get("descuento") or 0)
        detalle.append({"codigo": codigo, "cantidad": cant, "precio_unitario": base,
                        "bruto": bruto, "promocion": ev.get("promo"), "tipo_promo": ev.get("tipo"),
                        "descuento": float(ev.get("descuento") or 0),
                        "neto": float(ev.get("precio_final") or bruto)})
    subtotal = round(subtotal, 2)
    desc_promos = round(desc_promos, 2)
    base_post_promo = round(subtotal - desc_promos, 2)

    # Cupón (reutiliza fidelización). No se redime aquí.
    cupon_info, desc_cupon = None, 0.0
    if cupon:
        try:
            from src.db import fidelizacion as fid
            c = fid.validar_cupon(cupon, id_empresa=emp)
        except Exception:
            c = None
        if c:
            tipo, val = (c.get("tipo") or "descuento_pct"), float(c.get("valor") or 0)
            if tipo == "descuento_pct":
                desc_cupon = round(base_post_promo * val / 100.0, 2)
            elif tipo == "importe_fijo":
                desc_cupon = round(min(base_post_promo, val), 2)
            cupon_info = {"codigo": cupon, "tipo": tipo, "valor": val, "descuento": desc_cupon,
                          "valido": True}
        else:
            cupon_info = {"codigo": cupon, "valido": False, "descuento": 0.0}

    descuento_total = round(desc_promos + desc_cupon, 2)
    total = round(subtotal - descuento_total, 2)
    return {"moneda": moneda, "lista": lista, "lineas": detalle, "subtotal": subtotal,
            "descuento_promociones": desc_promos, "cupon": cupon_info,
            "descuento_cupon": desc_cupon, "descuento_total": descuento_total, "total": total}


def redimir_cupon(cupon, *, id_venta=None, id_empresa=None) -> bool:
    """Passthrough a fidelización (lo usará el checkout al confirmar). Reutilización."""
    try:
        from src.db import fidelizacion as fid
        return fid.redimir_cupon(cupon, id_venta=id_venta, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("redimir_cupon(%s): %s", cupon, e)
        return False


# ── Cross / Up-selling (ligero, reutiliza catálogo; IA degradable) ────────────
def sugerencias(id_publicacion, *, tipo="up", limite=5, id_empresa=None):
    """Sugerencias de venta. `up`: variantes de mayor precio (up-sell) desde el catálogo. `cross`:
    venta cruzada vía IA (capacidad, degradable → vacío). No inventa recomendaciones."""
    emp = _emp(id_empresa)
    if tipo == "up":
        try:
            from src.services.comercio_digital import catalogo
            vs = [v for v in catalogo.variantes(id_publicacion, id_empresa=emp)
                  if float(v.get("precio_delta") or 0) > 0]
            vs.sort(key=lambda v: float(v.get("precio_delta") or 0), reverse=True)
            return [{"sku": v["sku"], "atributos": v["atributos"],
                     "precio_delta": v["precio_delta"]} for v in vs[:limite]]
        except Exception as e:
            logger.debug("sugerencias up(%s): %s", id_publicacion, e)
            return []
    # cross-selling: degradable vía capacidad de IA (nunca acopla proveedor).
    try:
        from src.platform import capabilities as cap
        ia = cap.ia()
        if ia is not None and hasattr(ia, "agente"):
            ag = ia.agente("comercio")
            if hasattr(ag, "sugerir_cross_selling"):
                return (ag.sugerir_cross_selling(id_publicacion, id_empresa=emp) or [])[:limite]
    except Exception:
        pass
    return []


def descriptor() -> dict:
    return {"servicio": "cd_comercial", "etapa": "B", "fase": FASE, "estado": "implementado",
            "reutiliza": ["db.promociones", "db.fidelizacion", "catalogo"],
            "aporta": ["listas_precios", "cotizacion_unificada", "cross_up_selling"],
            "motor_promociones_nuevo": False, "mueve_stock": False, "crea_transaccion": False}


__all__ = ["FASE", "fijar_precio", "precio_de_lista", "cotizar", "redimir_cupon", "sugerencias",
           "descriptor"]
