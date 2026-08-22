"""
Motor de Precios Dinámicos + monitor de desvíos (Fase 3 del módulo Proveedores).

- `precio_referencia(codigo)`: índice de mercado = último coste de compra del artículo (histórico ERP).
- `evaluar_desvio(precio, ref, umbral)`: 'oportunidad' (precio < ref), 'alerta' (precio > ref+umbral%), 'normal'.
- `coste_mas_bajo(filas)`: menor coste unitario disponible en la bolsa (tarifa/b2b).
- `pvp_sugerido(coste, margen)`: PVP_Sugerido = coste * (1 + margen/100).
- `sugerencia_precio_venta(codigo, coste)`: sugerencia de actualización de PVP para inventario/ventas cuando
  la variación del coste es significativa (según el umbral y el margen objetivo configurados en Avanzado).

Reutiliza el histórico de compras del ERP y la config `db/compras_b2b`. No crea módulos nuevos.
"""

import logging

logger = logging.getLogger("compras.precios_dinamicos")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _uno(cur):
    r = cur.fetchone()
    if not r:
        return None
    v = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return v


def ref_manual(codigo, id_empresa=None) -> float | None:
    """Precio ref. FIJADO MANUALMENTE (articulos.precio_ref). None si la empresa no lo ha sobrescrito."""
    if not codigo:
        return None
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT precio_ref FROM articulos WHERE codigo=%s AND id_empresa<=>%s",
                        (str(codigo).strip(), emp))
            v = _uno(cur)
        return float(v) if v is not None else None
    except Exception as e:
        logger.debug("ref_manual(%s): %s", codigo, e)
        return None


def media_historica(codigo, id_empresa=None, dias=30) -> float | None:
    """Coste medio PONDERADO por cantidad de las líneas de pedido de los últimos `dias` días. None si no
    hay histórico en la ventana. Es el índice automático del Precio ref. cuando no hay valor manual."""
    if not codigo:
        return None
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT SUM(l.precio_unitario*l.cantidad)/NULLIF(SUM(l.cantidad),0) "
                "FROM compras_pedidos_lineas l JOIN compras_pedidos p ON p.id_pedido=l.id_pedido "
                "WHERE p.id_empresa<=>%s AND UPPER(l.codigo_articulo)=%s AND l.precio_unitario>0 "
                "AND l.cantidad>0 AND p.fecha >= (NOW() - INTERVAL %s DAY)",
                (emp, str(codigo).strip().upper(), int(dias)))
            v = _uno(cur)
        return round(float(v), 4) if v is not None else None
    except Exception as e:
        logger.debug("media_historica(%s): %s", codigo, e)
        return None


def _precio_alta(codigo, id_empresa=None) -> float | None:
    """Precio fijado en el alta del artículo (articulos.precio). Fallback para artículos sin histórico."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT precio FROM articulos WHERE codigo=%s AND id_empresa<=>%s",
                        (str(codigo).strip(), emp))
            v = _uno(cur)
        return float(v) if v not in (None, 0) else None
    except Exception as e:
        logger.debug("_precio_alta(%s): %s", codigo, e)
        return None


def precio_referencia(codigo, id_empresa=None) -> float | None:
    """Precio ref. del artículo, resuelto por prioridad:
    1) valor MANUAL fijado por la empresa (articulos.precio_ref);
    2) coste medio PONDERADO de los pedidos de los últimos 30 días (media histórica);
    3) precio de ALTA del artículo (articulos.precio) si no hay histórico.
    None solo si no hay ninguno de los tres."""
    if not codigo:
        return None
    emp = _emp(id_empresa)
    m = ref_manual(codigo, emp)
    if m is not None:
        return m
    mh = media_historica(codigo, emp)
    if mh is not None:
        return mh
    return _precio_alta(codigo, emp)


def es_ref_manual(codigo, id_empresa=None) -> bool:
    """True si el Precio ref. está fijado manualmente (prioritario, no se recalcula solo)."""
    return ref_manual(codigo, id_empresa) is not None


def set_precio_referencia(codigo, precio, id_empresa=None) -> bool:
    """Fija manualmente el Precio ref. del artículo (queda como referencia prioritaria)."""
    if not codigo:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE articulos SET precio_ref=%s WHERE codigo=%s AND id_empresa<=>%s",
                        (round(float(precio), 2), str(codigo).strip(), emp))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_precio_referencia(%s): %s", codigo, e)
        return False


def restablecer_precio_referencia(codigo, id_empresa=None) -> bool:
    """Quita el valor manual → el Precio ref. vuelve a calcularse por media histórica / precio de alta."""
    if not codigo:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE articulos SET precio_ref=NULL WHERE codigo=%s AND id_empresa<=>%s",
                        (str(codigo).strip(), emp))
            c.commit()
        return True
    except Exception as e:
        logger.error("restablecer_precio_referencia(%s): %s", codigo, e)
        return False


def evaluar_desvio(precio, ref, umbral_pct=10.0) -> str:
    """'oportunidad' | 'alerta' | 'normal' comparando un precio con el de referencia."""
    try:
        precio = float(precio)
        if ref in (None, "") or float(ref) <= 0:
            return "normal"
        ref = float(ref)
    except (TypeError, ValueError):
        return "normal"
    if precio < ref:
        return "oportunidad"
    if precio > ref * (1 + float(umbral_pct or 0) / 100.0):
        return "alerta"
    return "normal"


def coste_mas_bajo(filas) -> float | None:
    precios = [float(f.get("precio") or 0) for f in (filas or []) if float(f.get("precio") or 0) > 0]
    return min(precios) if precios else None


def pvp_sugerido(coste, margen_pct) -> float:
    return round(float(coste or 0) * (1 + float(margen_pct or 0) / 100.0), 2)


def _reglas(id_empresa=None):
    """(umbral_variacion_pct, margen_objetivo_pct) desde la config B2B/Avanzado (con defaults)."""
    try:
        from src.db import compras_b2b as cfgdb
        cfg = cfgdb.obtener_config(id_empresa)
        return float(cfg.get("umbral_variacion_pct") or 10.0), float(cfg.get("margen_objetivo_pct") or 30.0)
    except Exception:
        return 10.0, 30.0


# ── Watchlist (artículos monitorizados) ──────────────────────────────────────
def añadir_watchlist(codigo, id_empresa=None) -> bool:
    if not codigo:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT IGNORE INTO compras_watchlist (id_empresa, codigo_articulo) VALUES (%s,%s)",
                        (emp, str(codigo).strip().upper()))
            c.commit()
        return True
    except Exception as e:
        logger.error("añadir_watchlist: %s", e)
        return False


def quitar_watchlist(codigo, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM compras_watchlist WHERE id_empresa=%s AND codigo_articulo=%s",
                        (emp, str(codigo).strip().upper()))
            c.commit()
        return True
    except Exception as e:
        logger.error("quitar_watchlist: %s", e)
        return False


def en_watchlist(codigo, id_empresa=None) -> bool:
    """True si el artículo está en la watchlist (seguimiento crítico/estratégico) de la empresa."""
    if not codigo:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT 1 FROM compras_watchlist WHERE id_empresa=%s AND codigo_articulo=%s LIMIT 1",
                        (emp, str(codigo).strip().upper()))
            return cur.fetchone() is not None
    except Exception as e:
        logger.debug("en_watchlist(%s): %s", codigo, e)
        return False


def listar_watchlist(id_empresa=None) -> list:
    """Artículos monitorizados con su precio de referencia (para el visor de watchlist)."""
    emp = _emp(id_empresa)
    filas = []
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT codigo_articulo, creado_en FROM compras_watchlist WHERE id_empresa=%s "
                        "ORDER BY creado_en DESC", (emp,))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_watchlist: %s", e)
    for f in filas:
        f["precio_ref"] = precio_referencia(f.get("codigo_articulo"), emp)
    return filas


def sugerencia_precio_venta(codigo, coste, id_empresa=None) -> dict:
    """Sugerencia de PVP para inventario/ventas a partir del coste más bajo capturado.
    `significativo` es True si la variación del coste frente al de referencia supera el umbral."""
    emp = _emp(id_empresa)
    umbral, margen = _reglas(emp)
    ref = precio_referencia(codigo, emp)
    desvio = evaluar_desvio(coste, ref, umbral)
    variacion_pct = None
    if ref and coste:
        variacion_pct = round((float(coste) - float(ref)) / float(ref) * 100.0, 2)
    return {"codigo": codigo, "coste": (float(coste) if coste else None), "ref": ref,
            "margen_pct": margen, "umbral_pct": umbral, "pvp_sugerido": pvp_sugerido(coste, margen),
            "desvio": desvio, "variacion_pct": variacion_pct,
            "significativo": desvio in ("oportunidad", "alerta")}
