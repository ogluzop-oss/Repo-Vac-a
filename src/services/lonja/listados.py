"""Listados de la Lonja (ofertas vivas del mercado): publicar, consultar, retirar.

Un listado = artículo puesto a la venta por un vendedor, con precio de compra directa, puja mínima, divisa,
unidad y cantidad disponible. Visible por todas las empresas compradoras.
"""

import datetime as _dt

from ._common import _audit, _conn, _filas, _uno, logger

# Duración por defecto de una subasta si no se indica otra (horas). Toda subasta CADUCA.
DURACION_DEFECTO_HORAS = 24


def publicar(id_vendedor, codigo_articulo, precio, *, divisa=None, puja_minima=0, cantidad=1,
             unidad_medida="unidad", descripcion=None, permite_compra_directa=True, permite_puja=True,
             fecha_limite=None, duracion_horas=None, precio_reserva=None, incremento_minimo=0) -> int | None:
    """Publica un listado. `divisa` por defecto = la del vendedor. Si admite pujas y no se da
    `fecha_limite`, la subasta CADUCA a `duracion_horas` (o el defecto). `precio_reserva` = mínimo para
    adjudicar; `incremento_minimo` = subida mínima entre pujas."""
    try:
        from . import vendedores as _v
        if divisa is None:
            ven = _v.obtener(id_vendedor) or {}
            divisa = ven.get("divisa") or "EUR"
        cant = float(cantidad or 1)
        # Toda subasta tiene caducidad: si no hay fecha_limite explícita, se calcula por duración.
        if permite_puja and not fecha_limite:
            horas = float(duracion_horas or DURACION_DEFECTO_HORAS)
            fecha_limite = _dt.datetime.now() + _dt.timedelta(hours=horas)
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO lonja_listados (id_vendedor, codigo_articulo, descripcion, precio, "
                        "divisa, puja_minima, unidad_medida, cantidad, cantidad_disponible, "
                        "permite_compra_directa, permite_puja, fecha_limite, precio_reserva, "
                        "incremento_minimo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_vendedor, str(codigo_articulo).strip().upper(), descripcion, float(precio or 0),
                         str(divisa).upper()[:8], float(puja_minima or 0), str(unidad_medida or "unidad"),
                         cant, cant, 1 if permite_compra_directa else 0, 1 if permite_puja else 0,
                         fecha_limite, (float(precio_reserva) if precio_reserva not in (None, "") else None),
                         float(incremento_minimo or 0)))
            lid = cur.lastrowid
            c.commit()
        _audit("LONJA_LISTADO_ALTA", f"{lid}:{codigo_articulo}={precio}{divisa}", "lonja_listados")
        return lid
    except Exception as e:
        logger.error("publicar: %s", e)
        return None


def obtener(id_listado) -> dict | None:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT l.*, v.nombre AS vendedor FROM lonja_listados l "
                        "LEFT JOIN lonja_vendedores v ON v.id = l.id_vendedor WHERE l.id=%s", (id_listado,))
            return _uno(cur)
    except Exception as e:
        logger.error("obtener listado: %s", e)
        return None


def listar(codigo_articulo=None, *, id_vendedor=None, solo_activos=True) -> list:
    """Listados del mercado (todas las compradoras ven lo mismo). Filtrable por artículo/vendedor."""
    cond, params = [], []
    if codigo_articulo:
        cond.append("l.codigo_articulo=%s"); params.append(str(codigo_articulo).strip().upper())
    if id_vendedor:
        cond.append("l.id_vendedor=%s"); params.append(id_vendedor)
    if solo_activos:
        cond.append("l.estado='activo'")
    q = ("SELECT l.id, l.id_vendedor, v.nombre AS vendedor, l.codigo_articulo, l.descripcion, l.precio, "
         "l.divisa, l.puja_minima, l.unidad_medida, l.cantidad_disponible, l.permite_compra_directa, "
         "l.permite_puja, l.estado, l.fecha_limite, l.precio_reserva, l.incremento_minimo, l.creado_en "
         "FROM lonja_listados l LEFT JOIN lonja_vendedores v ON v.id = l.id_vendedor")
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY l.precio ASC, l.id DESC"
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("listar listados: %s", e)
        return []


def retirar(id_listado) -> bool:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_listados SET estado='retirado' WHERE id=%s AND estado='activo'",
                        (id_listado,))
            ok = cur.rowcount > 0
            c.commit()
        return ok
    except Exception as e:
        logger.error("retirar listado: %s", e)
        return False
