"""
Variantes de producto por TALLA y COLOR (edición Textil). Un producto "modelo" se despliega en variantes
(talla × color); cada variante es un SKU propio en `articulos` (precio/stock/código de barras), enlazado al
modelo padre por `producto_variantes`. Reutiliza el modelo de artículos/stock existente (N7). Multi-tenant.

La FUNCIÓN se muestra en las ediciones que la habilitan (`verticales.visible("productos.tallas")` → Supermarket,
Retail y Textil; oculta en Pharmacy/Bakery); el servicio es general y no depende de la edición.
"""

import logging
import re

from src.db.conexion import obtener_conexion

logger = logging.getLogger("productos.variantes")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _articulo(codigo, id_empresa):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, precio, id_familia, COALESCE(Stock_total,0) FROM articulos "
                        "WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            r = r if not isinstance(r, dict) else list(r.values())
            return {"nombre": r[0], "precio": r[1], "id_familia": r[2], "stock": int(r[3] or 0)}
    except Exception:
        return None


def _sku(codigo_padre, talla, color) -> str:
    def _n(s):
        return re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return f"{codigo_padre}-{_n(talla)}-{_n(color)}"


def crear_variantes(codigo_padre, *, tallas, colores, id_empresa=None, precio=None,
                    nombre_padre=None) -> dict:
    """Crea (o actualiza) las variantes talla × color del modelo `codigo_padre`. Cada variante es un SKU en
    `articulos` (hereda nombre/precio/familia del padre si existe). Idempotente. Devuelve {variantes, codigos}."""
    emp = _emp(id_empresa)
    if not emp or not codigo_padre or not tallas or not colores:
        return {"ok": False, "error": "faltan datos (padre/tallas/colores)", "variantes": 0}
    padre = _articulo(codigo_padre, emp)
    nombre_base = nombre_padre or (padre["nombre"] if padre else codigo_padre)
    precio_base = precio if precio is not None else (float(padre["precio"]) if padre else 0)
    id_familia = padre["id_familia"] if padre else None
    creadas, codigos = 0, []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for talla in tallas:
                for color in colores:
                    vcod = _sku(codigo_padre, talla, color)
                    cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, id_familia) "
                                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                                "precio=VALUES(precio), id_familia=VALUES(id_familia)",
                                (vcod, emp, f"{nombre_base} {talla}/{color}", precio_base, id_familia))
                    cur.execute("INSERT INTO producto_variantes (id_empresa, codigo_padre, codigo_variante, "
                                "talla, color) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                                "codigo_padre=VALUES(codigo_padre), talla=VALUES(talla), color=VALUES(color)",
                                (emp, codigo_padre, vcod, str(talla), str(color)))
                    creadas += 1
                    codigos.append(vcod)
            conn.commit()
    except Exception as e:
        logger.error("crear_variantes: %s", e)
        return {"ok": False, "error": str(e), "variantes": 0}
    return {"ok": True, "padre": codigo_padre, "variantes": creadas, "codigos": codigos}


def listar_variantes(codigo_padre, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT v.codigo_variante, v.talla, v.color, COALESCE(a.Stock_total,0), "
                        "COALESCE(a.precio,0) FROM producto_variantes v LEFT JOIN articulos a "
                        "ON a.codigo=v.codigo_variante AND a.id_empresa=v.id_empresa "
                        "WHERE v.id_empresa=%s AND v.codigo_padre=%s ORDER BY v.talla, v.color", (emp, codigo_padre))
            out = []
            for r in cur.fetchall():
                r = r if not isinstance(r, dict) else list(r.values())
                out.append({"codigo_variante": r[0], "talla": r[1], "color": r[2],
                            "stock": int(r[3] or 0), "precio": float(r[4] or 0)})
            return out
    except Exception as e:
        logger.debug("listar_variantes: %s", e)
        return []


def buscar_variante(codigo_padre, talla, color, id_empresa=None) -> str | None:
    """Código de la variante concreta (talla+color) del modelo, o None."""
    for v in listar_variantes(codigo_padre, id_empresa):
        if str(v["talla"]) == str(talla) and str(v["color"]) == str(color):
            return v["codigo_variante"]
    return None


def matriz(codigo_padre, id_empresa=None) -> dict:
    """Rejilla talla × color con el stock de cada variante (para la GUI de textil)."""
    vs = listar_variantes(codigo_padre, id_empresa)
    tallas = sorted({v["talla"] for v in vs}, key=lambda x: (len(str(x)), str(x)))
    colores = sorted({v["color"] for v in vs})
    idx = {(v["talla"], v["color"]): v for v in vs}
    celdas = []
    for t in tallas:
        for c in colores:
            v = idx.get((t, c))
            celdas.append({"talla": t, "color": c,
                           "codigo": v["codigo_variante"] if v else None,
                           "stock": v["stock"] if v else 0})
    return {"padre": codigo_padre, "tallas": tallas, "colores": colores, "celdas": celdas,
            "stock_total": sum(v["stock"] for v in vs)}
