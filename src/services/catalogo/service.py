"""
Servicio de catálogo: consulta el catálogo y lo serializa según el rol.

WEB PÚBLICA (cliente) y PANEL OPERATIVO (admin/gerente) comparten datos pero NO
campos: la vista pública nunca expone stock real, almacenes ni datos internos.
`serializar(prod, interno=...)` decide qué se muestra; `es_vista_interna(rol)`
resuelve el rol autenticado.
"""

import logging

from src.db import catalogo as cat

logger = logging.getLogger("catalogo_service")

# Roles con acceso a la vista operativa (interna).
_ROLES_INTERNOS = {"ADMINISTRADOR", "GERENTE", "SUPERADMIN"}


def es_vista_interna(rol=None) -> bool:
    """True si el rol ve la vista operativa. Si rol es None, usa la sesión activa."""
    if rol is None:
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or {}
            rol = u.get("rol") or u.get("perfil")
        except Exception:
            rol = None
    return str(rol or "").upper() in _ROLES_INTERNOS


# ── Serialización ────────────────────────────────────────────────────────────
def _precio_efectivo(prod) -> tuple[float, float, bool]:
    base = float(prod.get("precio") or 0)
    promo = bool(prod.get("promo_activa"))
    pp = float(prod.get("precio_promo") or 0)
    actual = pp if (promo and pp > 0) else base
    return actual, base, (promo and pp > 0)


def _imagen_portada(prod) -> str:
    imgs = cat.listar_imagenes(prod["id"]) if prod.get("id") else []
    if imgs:
        return imgs[0].get("url") or ""
    return prod.get("articulo_imagen") or ""


def serializar(prod: dict, interno: bool = False, detalle: bool = False) -> dict:
    """Serializa un producto del catálogo. `interno` añade datos operativos;
    `detalle` añade galería/atributos/variantes/relacionados."""
    if not prod:
        return {}
    actual, base, en_promo = _precio_efectivo(prod)
    stock_vendible = int(prod.get("stock_vendible") or 0)
    disponible = bool(stock_vendible > 0 and not prod.get("bloqueado")
                      and prod.get("visible_web", 1))
    out = {
        "id": prod.get("id"),
        "slug": prod.get("slug"),
        "nombre": prod.get("titulo_web") or prod.get("articulo_nombre"),
        "descripcion": prod.get("descripcion_web") or prod.get("articulo_desc"),
        "precio": round(actual, 2),
        "precio_base": round(base, 2),
        "en_promo": en_promo,
        "categoria": prod.get("categoria"),
        "marca": prod.get("marca"),
        "imagen": _imagen_portada(prod),
        "destacado": bool(prod.get("destacado")),
        "recomendado": bool(prod.get("recomendado")),
        "disponible": disponible,
    }
    if detalle:
        out["galeria"] = [i.get("url") for i in cat.listar_imagenes(prod["id"])]
        out["atributos"] = [{"nombre": a.get("nombre"), "valor": a.get("valor")}
                            for a in cat.listar_atributos_producto(prod["id"])]
        out["variantes"] = cat.listar_variantes(prod["id"])
        out["relacionados"] = [serializar(p, interno=interno)
                               for p in cat.relacionados_de(prod["id"], "relacionado")]
    if interno:
        # Datos operativos: NUNCA se exponen en la vista pública.
        out.update({
            "codigo_articulo": prod.get("codigo_articulo"),
            "stock_central": int(prod.get("stock_central") or 0),
            "stock_tienda": int(prod.get("stock_tienda") or 0),
            "stock_vendible": stock_vendible,
            "bloqueado": bool(prod.get("bloqueado")),
            "visible_web": bool(prod.get("visible_web", 1)),
            "id_categoria": prod.get("id_categoria"),
            "id_marca": prod.get("id_marca"),
            "orden": prod.get("orden"),
        })
        if detalle:
            out["stock_por_tienda"] = disponibilidad_por_tienda(prod.get("codigo_articulo"))
    return out


def _serializar_lista(prods, interno):
    return [serializar(p, interno=interno) for p in prods]


# ── API neutra (consumida por web pública / panel / conectores) ──────────────
def listar_categorias(arbol=True, solo_visibles=True, id_empresa=None):
    if arbol:
        return cat.arbol_categorias(solo_visibles=solo_visibles, id_empresa=id_empresa)
    return cat.listar_categorias(solo_visibles=solo_visibles, id_empresa=id_empresa)


def listar_productos(interno=None, categoria=None, marca=None, texto=None,
                     destacado=None, recomendado=None, id_empresa=None, limite=500):
    interno = es_vista_interna() if interno is None else interno
    prods = cat.listar_productos(
        categoria=categoria, marca=marca, destacado=destacado, recomendado=recomendado,
        solo_visibles=not interno, texto=texto, id_empresa=id_empresa, limite=limite)
    return _serializar_lista(prods, interno)


def producto(id_producto=None, slug=None, codigo_articulo=None, interno=None, id_empresa=None):
    interno = es_vista_interna() if interno is None else interno
    p = cat.obtener_producto(id_producto=id_producto, slug=slug,
                             codigo_articulo=codigo_articulo, id_empresa=id_empresa)
    if not p:
        return None
    if not interno and (not p.get("visible_web", 1) or p.get("bloqueado")):
        return None      # oculto para el público
    return serializar(p, interno=interno, detalle=True)


def destacados(interno=None, id_empresa=None, limite=50):
    interno = es_vista_interna() if interno is None else interno
    return _serializar_lista(
        cat.listar_productos(destacado=True, solo_visibles=not interno,
                             id_empresa=id_empresa, limite=limite), interno)


def recomendados(interno=None, id_empresa=None, limite=50):
    interno = es_vista_interna() if interno is None else interno
    return _serializar_lista(
        cat.listar_productos(recomendado=True, solo_visibles=not interno,
                             id_empresa=id_empresa, limite=limite), interno)


def buscar(texto, interno=None, id_empresa=None, limite=100):
    interno = es_vista_interna() if interno is None else interno
    return _serializar_lista(
        cat.listar_productos(texto=texto, solo_visibles=not interno,
                             id_empresa=id_empresa, limite=limite), interno)


# Conveniencia explícita por rol (para que la presentación no decida campos).
def vista_publica(**filtros):
    return listar_productos(interno=False, **filtros)


def vista_operativa(**filtros):
    return listar_productos(interno=True, **filtros)


# ── Disponibilidad operativa por tienda (omnicanal) ──────────────────────────
def disponibilidad_por_tienda(codigo_articulo, id_empresa=None) -> list:
    """Stock real del artículo en cada tienda de la empresa (vista operativa).
    Usa la tabla persistente `stock_tienda`. Devuelve [{tienda, codigo, stock}]."""
    if not codigo_articulo:
        return []
    try:
        from src.db.conexion import obtener_conexion, _filas_a_dicts
        from src.db.empresa import empresa_actual_id
        id_empresa = id_empresa or empresa_actual_id()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT t.id AS id_tienda, t.codigo_tienda, t.nombre AS tienda, "
                "COALESCE(st.stock,0) AS stock "
                "FROM tiendas t "
                "LEFT JOIN stock_tienda st ON st.id_tienda = t.id AND st.codigo_articulo = %s "
                "WHERE t.id_empresa = %s ORDER BY t.codigo_tienda",
                (codigo_articulo, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("disponibilidad_por_tienda(%s): %s", codigo_articulo, e)
        return []
