"""Estado de pedido reportado por el proveedor + stock declarado por el proveedor.

- ESTADO: `portal_pedido_estado` (uno vigente por pedido) capta lo que el proveedor dice del pedido
  (aceptado / en reparto / no disponible…). NO sustituye la máquina de estados de `compras_pedidos`
  (BORRADOR→ENVIADO→…→RECIBIDO): es la capa de seguimiento bidireccional que se muestra junto a ella.
- STOCK: `portal_proveedor_stock` es el stock que el proveedor declara por artículo/unidad; enriquece la
  bolsa de proveedores (saber quién tiene disponibilidad antes de pedir).
"""

from ._common import ESTADOS_PROVEEDOR, _audit, _conn, _emp, _filas, _uno, logger


def _norm_estado(e):
    e = str(e or "pendiente").strip().lower()
    return e if e in ESTADOS_PROVEEDOR else "pendiente"


def actualizar_estado_pedido(id_pedido, estado_proveedor, *, nota=None, id_proveedor=None,
                             id_empresa=None) -> bool:
    """Upsert del estado que el proveedor reporta de un pedido (uno vigente por pedido)."""
    emp = _emp(id_empresa)
    est = _norm_estado(estado_proveedor)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO portal_pedido_estado (id_empresa, id_pedido, id_proveedor, "
                        "estado_proveedor, nota) VALUES (%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE estado_proveedor=VALUES(estado_proveedor), "
                        "nota=VALUES(nota), id_proveedor=COALESCE(VALUES(id_proveedor),id_proveedor), "
                        "actualizado_en=NOW()",
                        (emp, id_pedido, id_proveedor, est, (nota or None)))
            c.commit()
        _audit("PORTAL_PEDIDO_ESTADO", f"{id_pedido}:{est}", "portal_pedido_estado")
        return True
    except Exception as e:
        logger.error("actualizar_estado_pedido: %s", e)
        return False


def estado_pedido(id_pedido, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id_pedido, id_proveedor, estado_proveedor, nota, actualizado_en "
                        "FROM portal_pedido_estado WHERE id_empresa=%s AND id_pedido=%s", (emp, id_pedido))
            return _uno(cur)
    except Exception as e:
        logger.error("estado_pedido: %s", e)
        return None


def estados_pedidos(id_empresa=None, ids=None) -> dict:
    """{id_pedido: estado_proveedor} para pintar el seguimiento en Recepciones sin N consultas."""
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if ids:
        marcas = ",".join(["%s"] * len(ids))
        cond.append(f"id_pedido IN ({marcas})"); params.extend(list(ids))
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id_pedido, estado_proveedor FROM portal_pedido_estado "
                        "WHERE " + " AND ".join(cond), tuple(params))
            return {r["id_pedido"]: r["estado_proveedor"] for r in _filas(cur)}
    except Exception as e:
        logger.error("estados_pedidos: %s", e)
        return {}


def pedidos_de_proveedor(id_proveedor, id_empresa=None, estados=("ENVIADO", "PARCIAL")) -> list:
    """Vista del PROVEEDOR: sus pedidos en curso (reutiliza `db.compras.listar_pedidos`) + el estado
    portal que él mismo reporta."""
    from src.db import compras as C
    emp = _emp(id_empresa)
    salida = []
    try:
        peds = C.listar_pedidos(id_empresa=emp, id_proveedor=id_proveedor)
    except Exception as e:
        logger.error("pedidos_de_proveedor: %s", e)
        return []
    mapa = estados_pedidos(id_empresa=emp, ids=[p["id_pedido"] for p in peds] or None)
    for p in peds:
        if estados and p.get("estado") not in estados:
            continue
        p = dict(p)
        p["estado_proveedor"] = mapa.get(p["id_pedido"], "pendiente")
        salida.append(p)
    return salida


# ── Stock declarado por el proveedor ─────────────────────────────────────────
def set_stock(id_proveedor, codigo_articulo, stock, *, unidad_medida="unidad", id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO portal_proveedor_stock (id_empresa, id_proveedor, codigo_articulo, "
                        "stock, unidad_medida) VALUES (%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE stock=VALUES(stock), actualizado_en=NOW()",
                        (emp, id_proveedor, str(codigo_articulo).strip().upper(), float(stock or 0),
                         str(unidad_medida or "unidad")))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_stock: %s", e)
        return False


def stock_de(id_proveedor, codigo_articulo=None, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "id_proveedor=%s"], [emp, id_proveedor]
    if codigo_articulo:
        cond.append("codigo_articulo=%s"); params.append(str(codigo_articulo).strip().upper())
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT codigo_articulo, stock, unidad_medida, actualizado_en "
                        "FROM portal_proveedor_stock WHERE " + " AND ".join(cond)
                        + " ORDER BY codigo_articulo", tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("stock_de: %s", e)
        return []


def stock_bolsa(codigo_articulo, id_empresa=None) -> dict:
    """{id_proveedor: stock} de un artículo, para enriquecer la bolsa de proveedores."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id_proveedor, SUM(stock) AS stock FROM portal_proveedor_stock "
                        "WHERE id_empresa=%s AND codigo_articulo=%s GROUP BY id_proveedor",
                        (emp, str(codigo_articulo).strip().upper()))
            return {r["id_proveedor"]: float(r["stock"] or 0) for r in _filas(cur)}
    except Exception as e:
        logger.error("stock_bolsa: %s", e)
        return {}
