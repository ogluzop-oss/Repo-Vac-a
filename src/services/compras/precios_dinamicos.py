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


def precio_referencia(codigo, id_empresa=None) -> float | None:
    """Último precio unitario de compra del artículo (índice de mercado). None si no hay histórico."""
    if not codigo:
        return None
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT l.precio_unitario FROM compras_pedidos_lineas l "
                "JOIN compras_pedidos p ON p.id_pedido=l.id_pedido "
                "WHERE p.id_empresa=%s AND UPPER(l.codigo_articulo)=%s AND l.precio_unitario>0 "
                "ORDER BY l.id_pedido DESC LIMIT 1", (emp, str(codigo).strip().upper()))
            r = cur.fetchone()
        if r:
            v = r[0] if not isinstance(r, dict) else list(r.values())[0]
            return float(v) if v else None
    except Exception as e:
        logger.debug("precio_referencia(%s): %s", codigo, e)
    return None


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
