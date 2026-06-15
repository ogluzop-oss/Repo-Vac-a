"""
Capa de datos del CATÁLOGO ONLINE (Fase 2 — omnicanal).

Es una capa de presentación SOBRE `articulos`: cada producto de catálogo
referencia `articulos.codigo` (única fuente de stock/precio) y añade los datos
web (categoría, marca, galería, atributos, variantes, etiquetas, destacados…).

Todo está aislado por `id_empresa` (y opcionalmente `id_tienda`), respetando la
arquitectura multiempresa/multitienda. Neutro respecto a la capa de presentación:
lo consumen tanto la web pública como el panel operativo y los conectores de
e-commerce. Ver [[project_venta_online]].
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion)

logger = logging.getLogger("catalogo_db")


# ── Contexto de tenant ───────────────────────────────────────────────────────
def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _tienda(id_tienda="auto"):
    if id_tienda != "auto":
        return id_tienda
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def _slug(texto: str) -> str:
    import re
    try:
        from unidecode import unidecode
        texto = unidecode(texto or "")
    except Exception:
        texto = texto or ""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", texto.lower()).strip("-")
    return s or "item"


# ── Categorías (autorreferencial: categoría/subcategoría) ────────────────────
def crear_categoria(nombre, parent_id=None, descripcion=None, imagen=None,
                    orden=0, id_tienda=None, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO catalogo_categorias "
                "(id_empresa, id_tienda, parent_id, nombre, slug, descripcion, imagen, orden) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_tienda, parent_id, nombre, _slug(nombre),
                 descripcion, imagen, orden))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_categoria: %s", e)
        return None


def listar_categorias(parent_id="all", solo_visibles=False, id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if parent_id != "all":
        if parent_id is None:
            filtros.append("parent_id IS NULL")
        else:
            filtros.append("parent_id=%s"); params.append(parent_id)
    if solo_visibles:
        filtros.append("visible=1")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_categorias WHERE " + " AND ".join(filtros)
                        + " ORDER BY orden, nombre", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_categorias: %s", e)
        return []


def arbol_categorias(solo_visibles=False, id_empresa=None) -> list:
    """Categorías en árbol (cada nodo con 'hijos')."""
    todas = listar_categorias(parent_id="all", solo_visibles=solo_visibles, id_empresa=id_empresa)
    por_id = {c["id"]: dict(c, hijos=[]) for c in todas}
    raiz = []
    for c in por_id.values():
        padre = por_id.get(c.get("parent_id"))
        (padre["hijos"] if padre else raiz).append(c)
    return raiz


# ── Marcas / etiquetas ───────────────────────────────────────────────────────
def crear_marca(nombre, logo=None, descripcion=None, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO catalogo_marcas (id_empresa, nombre, slug, logo, descripcion) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, nombre, _slug(nombre), logo, descripcion))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_marca: %s", e)
        return None


def listar_marcas(id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_marcas WHERE id_empresa=%s ORDER BY nombre",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_marcas: %s", e)
        return []


def crear_etiqueta(nombre, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO catalogo_etiquetas (id_empresa, nombre, slug) VALUES (%s,%s,%s)",
                        (id_empresa, nombre, _slug(nombre)))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_etiqueta: %s", e)
        return None


def listar_etiquetas(id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_etiquetas WHERE id_empresa=%s ORDER BY nombre",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_etiquetas: %s", e)
        return []


# ── Productos (overlay sobre articulos) ──────────────────────────────────────
_CAMPOS_PROD = ("id_categoria", "id_marca", "titulo_web", "descripcion_web",
                "destacado", "recomendado", "visible_web", "orden",
                "seo_title", "seo_descripcion", "id_tienda")


def upsert_producto(codigo_articulo, id_empresa=None, **campos) -> int | None:
    """Crea o actualiza el overlay de catálogo de un artículo (único por empresa).
    Solo toca los campos indicados en ``campos`` (subset de _CAMPOS_PROD)."""
    id_empresa = _empresa(id_empresa)
    datos = {k: v for k, v in campos.items() if k in _CAMPOS_PROD}
    slug = campos.get("slug") or _slug(campos.get("titulo_web") or codigo_articulo)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM catalogo_productos WHERE id_empresa=%s AND codigo_articulo=%s",
                        (id_empresa, codigo_articulo))
            fila = cur.fetchone()
            if fila:
                pid = fila[0] if not isinstance(fila, dict) else fila["id"]
                if datos:
                    sets = ", ".join(f"{k}=%s" for k in datos)
                    cur.execute(f"UPDATE catalogo_productos SET {sets} WHERE id=%s",
                                (*datos.values(), pid))
                    conn.commit()
                return pid
            cols = ["id_empresa", "codigo_articulo", "slug"] + list(datos.keys())
            vals = [id_empresa, codigo_articulo, slug] + list(datos.values())
            cur.execute(f"INSERT INTO catalogo_productos ({', '.join(cols)}) "
                        f"VALUES ({', '.join(['%s'] * len(cols))})", tuple(vals))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("upsert_producto(%s): %s", codigo_articulo, e)
        return None


def _select_productos(where, params, limite=500):
    """SELECT de productos con JOIN a articulos (nombre/precio/stock reales)."""
    sql = (
        "SELECT p.*, a.nombre AS articulo_nombre, a.descripcion AS articulo_desc, "
        "a.precio AS precio, a.promo_activa, a.precio_promo, "
        "a.Stock_total AS stock_central, a.Stock_tienda AS stock_tienda, "
        "(COALESCE(a.Stock_total,0)+COALESCE(a.Stock_tienda,0)) AS stock_vendible, "
        "a.bloqueado, a.imagen AS articulo_imagen, m.nombre AS marca, c.nombre AS categoria "
        "FROM catalogo_productos p "
        "JOIN articulos a ON a.codigo = p.codigo_articulo "
        "LEFT JOIN catalogo_marcas m ON m.id = p.id_marca "
        "LEFT JOIN catalogo_categorias c ON c.id = p.id_categoria "
        "WHERE " + where + " ORDER BY p.orden, a.nombre LIMIT %s")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_select_productos: %s", e)
        return []


def listar_productos(categoria=None, marca=None, destacado=None, recomendado=None,
                     solo_visibles=False, texto=None, id_empresa=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["p.id_empresa=%s"], [id_empresa]
    if categoria is not None:
        filtros.append("p.id_categoria=%s"); params.append(categoria)
    if marca is not None:
        filtros.append("p.id_marca=%s"); params.append(marca)
    if destacado is not None:
        filtros.append("p.destacado=%s"); params.append(1 if destacado else 0)
    if recomendado is not None:
        filtros.append("p.recomendado=%s"); params.append(1 if recomendado else 0)
    if solo_visibles:
        filtros.append("p.visible_web=1 AND COALESCE(a.bloqueado,0)=0")
    if texto:
        filtros.append("(a.nombre LIKE %s OR p.titulo_web LIKE %s OR a.codigo LIKE %s)")
        params += [f"%{texto}%"] * 3
    return _select_productos(" AND ".join(filtros), params, limite)


def obtener_producto(id_producto=None, codigo_articulo=None, slug=None, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    if id_producto is not None:
        cond, val = "p.id=%s", id_producto
    elif codigo_articulo is not None:
        cond, val = "p.codigo_articulo=%s", codigo_articulo
    elif slug is not None:
        cond, val = "p.slug=%s", slug
    else:
        return None
    filas = _select_productos(f"p.id_empresa=%s AND {cond}", [id_empresa, val], limite=1)
    return filas[0] if filas else None


def eliminar_producto(id_producto, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("catalogo_imagenes", "catalogo_producto_atributos",
                      "catalogo_variantes", "catalogo_producto_etiquetas"):
                cur.execute(f"DELETE FROM {t} WHERE id_producto=%s", (id_producto,))
            cur.execute("DELETE FROM catalogo_relacionados WHERE id_producto=%s OR id_producto_rel=%s",
                        (id_producto, id_producto))
            cur.execute("DELETE FROM catalogo_productos WHERE id=%s AND id_empresa=%s",
                        (id_producto, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("eliminar_producto(%s): %s", id_producto, e)
        return False


# ── Imágenes / galería ───────────────────────────────────────────────────────
def anadir_imagen(id_producto, url, alt=None, orden=0, es_portada=False, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO catalogo_imagenes (id_empresa, id_producto, url, alt, orden, es_portada) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_producto, url, alt, orden, 1 if es_portada else 0))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("anadir_imagen: %s", e)
        return None


def listar_imagenes(id_producto) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_imagenes WHERE id_producto=%s "
                        "ORDER BY es_portada DESC, orden", (id_producto,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_imagenes: %s", e)
        return []


# ── Atributos / variantes ────────────────────────────────────────────────────
def set_atributo_producto(id_producto, nombre, valor, id_atributo=None, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO catalogo_producto_atributos "
                        "(id_empresa, id_producto, id_atributo, nombre, valor) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, id_producto, id_atributo, nombre, valor))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("set_atributo_producto: %s", e)
        return None


def listar_atributos_producto(id_producto) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_producto_atributos WHERE id_producto=%s", (id_producto,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_atributos_producto: %s", e)
        return []


def crear_variante(id_producto, sku=None, nombre=None, codigo_articulo=None,
                   precio_dif=0, atributos=None, orden=0, id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    import json
    atr = json.dumps(atributos) if isinstance(atributos, (dict, list)) else atributos
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO catalogo_variantes "
                        "(id_empresa, id_producto, codigo_articulo, sku, nombre, precio_dif, atributos, orden) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_producto, codigo_articulo, sku, nombre,
                         precio_dif, atr, orden))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_variante: %s", e)
        return None


def listar_variantes(id_producto) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM catalogo_variantes WHERE id_producto=%s ORDER BY orden", (id_producto,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_variantes: %s", e)
        return []


# ── Etiquetas (M:N) y relacionados / recomendados ────────────────────────────
def etiquetar_producto(id_producto, id_etiqueta, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO catalogo_producto_etiquetas "
                        "(id_empresa, id_producto, id_etiqueta) VALUES (%s,%s,%s)",
                        (id_empresa, id_producto, id_etiqueta))
            conn.commit()
        return True
    except Exception as e:
        logger.error("etiquetar_producto: %s", e)
        return False


def relacionar_productos(id_producto, id_producto_rel, tipo="relacionado", id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO catalogo_relacionados "
                        "(id_empresa, id_producto, id_producto_rel, tipo) VALUES (%s,%s,%s,%s)",
                        (id_empresa, id_producto, id_producto_rel, tipo))
            conn.commit()
        return True
    except Exception as e:
        logger.error("relacionar_productos: %s", e)
        return False


def relacionados_de(id_producto, tipo="relacionado", id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    filas = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_producto_rel FROM catalogo_relacionados "
                        "WHERE id_empresa=%s AND id_producto=%s AND tipo=%s",
                        (id_empresa, id_producto, tipo))
            ids = [r[0] if not isinstance(r, dict) else r["id_producto_rel"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("relacionados_de: %s", e)
        return []
    for pid in ids:
        p = obtener_producto(id_producto=pid, id_empresa=id_empresa)
        if p:
            filas.append(p)
    return filas
