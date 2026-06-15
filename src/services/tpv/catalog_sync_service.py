"""
Sincronización de catálogo hacia la plataforma de e-commerce (push de precios y
existencias). Complementa el pull de pedidos (`online_orders_service`).

La plataforma de venta online debe reflejar el precio y el stock reales del
sistema. Este servicio lee los artículos de la empresa activa y los empuja al
adaptador configurado (WooCommerce/Shopify); el emparejamiento es por SKU = código
de artículo. Degrada con elegancia (sin credenciales/red → no hace nada).
Ver [[project_venta_online]].
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("catalog_sync")


def _ctx_empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def articulos_para_sync(id_empresa=None) -> list:
    """Artículos a publicar: [{codigo, nombre, precio, stock}] de la empresa activa.

    ``stock`` = existencias vendibles (central + tienda de trabajo). Excluye los
    artículos bloqueados."""
    id_empresa = _ctx_empresa(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, COALESCE(precio,0), "
                "COALESCE(Stock_total,0) + COALESCE(Stock_tienda,0) AS stock "
                "FROM articulos WHERE id_empresa=%s AND COALESCE(bloqueado,0)=0",
                (id_empresa,))
            for r in cur.fetchall():
                codigo, nombre, precio, stock = (r if not isinstance(r, dict) else
                                                 (r["codigo"], r["nombre"], r["precio"], r["stock"]))
                if codigo:
                    out.append({"codigo": codigo, "nombre": nombre,
                                "precio": float(precio or 0), "stock": int(stock or 0)})
    except Exception as e:
        logger.error("articulos_para_sync: %s", e)
    return out


def sincronizar_catalogo(id_empresa=None) -> dict:
    """Empuja precio+stock de todo el catálogo a la plataforma configurada.
    Devuelve {ok, total, actualizados, fallidos, plataforma}."""
    arts = articulos_para_sync(id_empresa)
    try:
        from src.services.tpv.ecommerce import adaptador_actual
        ad = adaptador_actual()
        plataforma = getattr(ad, "nombre", "web")
        if not ad.configurado():
            return {"ok": False, "total": len(arts), "actualizados": 0,
                    "fallidos": len(arts), "plataforma": plataforma,
                    "motivo": "sin_config"}
        res = ad.sincronizar_catalogo(arts)
    except Exception as e:
        logger.error("sincronizar_catalogo: %s", e)
        return {"ok": False, "total": len(arts), "actualizados": 0,
                "fallidos": len(arts), "plataforma": "web", "motivo": str(e)}
    res["plataforma"] = plataforma
    _auditar(f"{plataforma}:{res.get('actualizados', 0)}/{res.get('total', 0)}")
    return res


def sincronizar_articulo(codigo: str) -> bool:
    """Empuja precio+stock de UN artículo a la plataforma (tras un cambio puntual)."""
    arts = [a for a in articulos_para_sync() if str(a["codigo"]) == str(codigo)]
    if not arts:
        return False
    a = arts[0]
    try:
        from src.services.tpv.ecommerce import adaptador_actual
        ad = adaptador_actual()
        if not ad.configurado():
            return False
        ok = bool(ad.actualizar_articulo(a["codigo"], a["precio"], a["stock"], a["nombre"]))
    except Exception as e:
        logger.error("sincronizar_articulo(%s): %s", codigo, e)
        return False
    if ok:
        _auditar(f"articulo:{codigo}")
    return ok


def _auditar(detalle: str) -> None:
    try:
        from src.db.conexion import log_auditoria
        usuario = "sistema"
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or {}
            usuario = u.get("nombre") or u.get("usuario") or "sistema"
        except Exception:
            pass
        log_auditoria(usuario, "SINCRONIZAR_CATALOGO_ONLINE", "articulos", detalle)
    except Exception as e:
        logger.debug("auditar sync: %s", e)
