"""Capa de datos de la ANALÍTICA de ventas (dashboard `gui/ventas`): histórico de previsión,
objetivos anuales, series de ventas del TPV, top de artículos y rendimiento diario.

Fase 3 · cliente fino: extraído de `gui/ventas` para que la ventana no ejecute SQL directo. La GUI
solo orquesta (gráficas, tablas, IA); aquí viven las consultas/escrituras y el filtro de tenant.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("ventas.analitica")


def _tenant_filtro(alias=None, id_empresa=None, id_tienda=None):
    """Fragmento WHERE + params para aislar por empresa/tienda. `alias` = prefijo de tabla. Si se pasa
    `id_empresa` explícito (REST, sin sesión de escritorio) se usa tal cual; si no, cae en la
    empresa/tienda ACTIVAS de sesión (comportamiento de escritorio intacto)."""
    p = f"{alias}." if alias else ""
    if id_empresa is not None:
        frag = f" AND {p}id_empresa=%s"
        params = [id_empresa]
        if id_tienda is not None:
            frag += f" AND {p}id_tienda=%s"
            params.append(id_tienda)
        return frag, params
    from src.db.empresa import empresa_actual_id, tienda_actual_id_int
    frag = f" AND {p}id_empresa=%s"
    params = [empresa_actual_id()]
    tid = tienda_actual_id_int()
    if tid is not None:
        frag += f" AND {p}id_tienda=%s"
        params.append(tid)
    return frag, params


# ── Histórico de ventas ───────────────────────────────────────────────────────────────────────────
# Fuente ÚNICA: `ventas_historicas` (`db/ventas_historicas.py`), alimentada por el módulo
# centralizado "Migrar datos" (`services.importacion`, entidad VENTAS_HIST) — la antigua tabla
# `prevision_historico` (subida directa desde `gui/ventas.py`, sin aislamiento por empresa) queda
# retirada: estas funciones ahora agregan sobre `ventas_historicas` (per-artículo), que sí aísla por
# `id_empresa`. Mismas firmas/formas de retorno que antes — los llamantes (`gui/ventas.py`) no
# necesitan cambios, solo pasan a ver los datos importados desde el wizard centralizado.
def resumen_historico(id_empresa=None) -> list:
    """[(anio, dias, total, fuente)] agrupado por año. `fuente` siempre 'IMPORTADO' (único origen
    posible de las filas de `ventas_historicas`: la importación centralizada)."""
    from src.db.empresa import empresa_actual_id
    eid = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT YEAR(fecha) AS anio, COUNT(DISTINCT fecha) AS dias, "
                "COALESCE(SUM(importe),0) AS total, 'IMPORTADO' AS fuente "
                "FROM ventas_historicas WHERE id_empresa=%s GROUP BY anio ORDER BY anio DESC",
                (eid,))
            return list(cur.fetchall())
    except Exception as e:
        logger.error("resumen_historico: %s", e)
        return []


def contar_historico(id_empresa=None) -> int:
    from src.db.empresa import empresa_actual_id
    eid = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ventas_historicas WHERE id_empresa=%s", (eid,))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


def serie_historico(id_empresa=None) -> list:
    """[(fecha, total_importe)] agrupado por fecha (varios artículos pueden compartir fecha)."""
    from src.db.empresa import empresa_actual_id
    eid = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fecha, SUM(importe) FROM ventas_historicas WHERE id_empresa=%s "
                       "GROUP BY fecha ORDER BY fecha", (eid,))
            return list(cur.fetchall())
    except Exception as e:
        logger.error("serie_historico: %s", e)
        return []


def serie_historico_agrupada(id_empresa=None) -> list:
    """[(fecha, SUM(importe))] agrupado por fecha (para la IA predictiva de `gui/ventas.py`) —
    mismo resultado que `serie_historico`, se conserva como función independiente por
    compatibilidad de los llamantes existentes."""
    return serie_historico(id_empresa)


# ── Objetivos anuales ──────────────────────────────────────────────────────────────────────────────
def objetivo_anual(anio):
    """Objetivo anual (float) del año o None."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT objetivo_anual FROM prevision_objetivos WHERE anio=%s", (anio,))
            r = cur.fetchone()
            v = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            return float(v) if v else None
    except Exception:
        return None


def guardar_objetivo(anio, objetivo, ruta_excel) -> bool:
    """Upsert del objetivo anual + marca excel generado."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO prevision_objetivos (anio, objetivo_anual, excel_generado, ruta_excel_drive) "
                        "VALUES (%s,%s,1,%s) ON DUPLICATE KEY UPDATE excel_generado=1, ruta_excel_drive=%s",
                        (anio, objetivo, ruta_excel, ruta_excel))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_objetivo: %s", e)
        return False


# ── Series de ventas (TPV) + top de artículos (aislado por tenant) ──────────────────────────────────
def serie_por_dia(desde, hasta, art=None, secc=None, *, id_empresa=None, id_tienda=None) -> list:
    """[(dia, total)] de ventas por día entre `desde` y `hasta`; opcional por artículo o sección."""
    tf, tp = _tenant_filtro("v", id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if art:
                cur.execute("SELECT DATE(v.fecha) AS dia, SUM(vi.subtotal) AS total "
                            "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                            "WHERE DATE(v.fecha) BETWEEN %s AND %s AND (vi.codigo_articulo=%s OR vi.nombre LIKE %s)"
                            + tf + " GROUP BY dia ORDER BY dia", (desde, hasta, art, f"%{art}%", *tp))
            elif secc:
                cur.execute("SELECT DATE(v.fecha) AS dia, SUM(vi.subtotal) AS total "
                            "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                            "WHERE DATE(v.fecha) BETWEEN %s AND %s AND vi.seccion=%s"
                            + tf + " GROUP BY dia ORDER BY dia", (desde, hasta, secc, *tp))
            else:
                cur.execute("SELECT DATE(v.fecha) AS dia, SUM(v.total) AS total "
                            "FROM ventas v WHERE DATE(v.fecha) BETWEEN %s AND %s"
                            + tf + " GROUP BY dia ORDER BY dia", (desde, hasta, *tp))
            return list(cur.fetchall())
    except Exception as e:
        logger.error("serie_por_dia: %s", e)
        return []


def serie_por_hora(fecha, art=None, secc=None, *, id_empresa=None, id_tienda=None) -> list:
    """[(hora, total)] de ventas por hora del día `fecha`, para las horas 8-22 inclusive
    (zero-fill: horas sin ventas devuelven total=0, para que la gráfica horaria dibuje el
    tramo 08:00-22:00 completo). Opcional por artículo o sección. Análogo a `serie_por_dia`,
    agrupando por `HOUR(v.fecha)` en vez de `DATE(v.fecha)` y acotando al día/franja horaria;
    reutiliza el mismo `_tenant_filtro` (ningún mecanismo de aislamiento paralelo)."""
    tf, tp = _tenant_filtro("v", id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if art:
                cur.execute("SELECT HOUR(v.fecha) AS hora, SUM(vi.subtotal) AS total "
                            "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                            "WHERE DATE(v.fecha)=%s AND HOUR(v.fecha) BETWEEN 8 AND 22 "
                            "AND (vi.codigo_articulo=%s OR vi.nombre LIKE %s)"
                            + tf + " GROUP BY hora ORDER BY hora", (fecha, art, f"%{art}%", *tp))
            elif secc:
                cur.execute("SELECT HOUR(v.fecha) AS hora, SUM(vi.subtotal) AS total "
                            "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                            "WHERE DATE(v.fecha)=%s AND HOUR(v.fecha) BETWEEN 8 AND 22 AND vi.seccion=%s"
                            + tf + " GROUP BY hora ORDER BY hora", (fecha, secc, *tp))
            else:
                cur.execute("SELECT HOUR(v.fecha) AS hora, SUM(v.total) AS total "
                            "FROM ventas v WHERE DATE(v.fecha)=%s AND HOUR(v.fecha) BETWEEN 8 AND 22"
                            + tf + " GROUP BY hora ORDER BY hora", (fecha, *tp))
            filas = {int(r[0]): float(r[1] or 0) for r in cur.fetchall()}
            return [(h, filas.get(h, 0.0)) for h in range(8, 23)]
    except Exception as e:
        logger.error("serie_por_hora: %s", e)
        return []


def top_articulos(desde, hasta, secc=None, limite=10, *, id_empresa=None, id_tienda=None) -> list:
    """[(codigo, nombre, uds)] de los artículos más vendidos en el rango; opcional por sección."""
    tf, tp = _tenant_filtro("v", id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT vi.codigo_articulo, vi.nombre, SUM(vi.cantidad) AS uds "
                        "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                        "WHERE DATE(v.fecha) BETWEEN %s AND %s "
                        + ("AND vi.seccion=%s " if secc else "") + tf
                        + " GROUP BY vi.codigo_articulo, vi.nombre ORDER BY uds DESC LIMIT %s",
                        ((desde, hasta, secc, *tp, int(limite)) if secc else (desde, hasta, *tp, int(limite))))
            return list(cur.fetchall())
    except Exception as e:
        logger.error("top_articulos: %s", e)
        return []


def resumen_periodo(desde, hasta, *, id_empresa=None, id_tienda=None) -> dict:
    """{'facturacion', 'tickets', 'ticket_medio', 'unidades', 'unidades_ticket', 'ventas_cruzadas',
    'ventas_promocionales'} del rango `desde`..`hasta` (fechas, inclusive) — mismo criterio que
    `services.bi.calculadores` (`ventas.num_tickets`/`ticket_medio`), pero ya acotado por
    tienda/rango EXPLÍCITOS (no el período fijo del BI), para alimentar la franja de KPIs de
    "Resumen de Ventas" (petición explícita: Tickets/Conversión/Facturación/Unidades por ticket/
    Ventas cruzadas/Ventas promocionales junto al Capture Rate de tráfico).

    `ventas_cruzadas`/`ventas_promocionales` = unidades vendidas de artículos marcados
    `es_complementario`/`es_promocional` (migr. 0320, Alta artículo del Portal Empresa) — mismo
    criterio de "unidades", no de líneas de venta."""
    tf, tp = _tenant_filtro("v", id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(v.total),0), COUNT(*) FROM ventas v "
                        "WHERE DATE(v.fecha) BETWEEN %s AND %s" + tf, (desde, hasta, *tp))
            fila = cur.fetchone() or (0, 0)
            facturacion = float(fila[0] or 0)
            tickets = int(fila[1] or 0)
            ticket_medio = round(facturacion / tickets, 2) if tickets else 0.0

            cur.execute(
                "SELECT COALESCE(SUM(vi.cantidad),0), "
                "COALESCE(SUM(CASE WHEN a.es_complementario=1 THEN vi.cantidad ELSE 0 END),0), "
                "COALESCE(SUM(CASE WHEN a.es_promocional=1 THEN vi.cantidad ELSE 0 END),0) "
                "FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                "LEFT JOIN articulos a ON a.codigo=vi.codigo_articulo AND a.id_empresa=v.id_empresa "
                "WHERE DATE(v.fecha) BETWEEN %s AND %s" + tf, (desde, hasta, *tp))
            fila2 = cur.fetchone() or (0, 0, 0)
            unidades = float(fila2[0] or 0)
            ventas_cruzadas = float(fila2[1] or 0)
            ventas_promocionales = float(fila2[2] or 0)
            unidades_ticket = round(unidades / tickets, 2) if tickets else 0.0

            return {"facturacion": facturacion, "tickets": tickets, "ticket_medio": ticket_medio,
                    "unidades": unidades, "unidades_ticket": unidades_ticket,
                    "ventas_cruzadas": ventas_cruzadas, "ventas_promocionales": ventas_promocionales}
    except Exception as e:
        logger.error("resumen_periodo: %s", e)
        return {"facturacion": 0.0, "tickets": 0, "ticket_medio": 0.0, "unidades": 0.0,
                "unidades_ticket": 0.0, "ventas_cruzadas": 0.0, "ventas_promocionales": 0.0}


def secciones_disponibles(*, id_empresa=None, id_tienda=None) -> list:
    """Secciones distintas con ventas registradas (para el filtro del móvil/dashboard)."""
    tf, tp = _tenant_filtro("v", id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT vi.seccion FROM ventas v JOIN venta_items vi ON vi.venta_id=v.id "
                        "WHERE vi.seccion IS NOT NULL AND vi.seccion<>''" + tf + " ORDER BY vi.seccion", tp)
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        logger.error("secciones_disponibles: %s", e)
        return []


def serie_ventas_tpv() -> list:
    """[(DATE(fecha), SUM(total))] de todas las ventas del TPV (aislado por tenant)."""
    tf, tp = _tenant_filtro()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DATE(fecha), COALESCE(SUM(total),0) FROM ventas WHERE 1=1"
                        + tf + " GROUP BY DATE(fecha) ORDER BY DATE(fecha)", tp)
            return list(cur.fetchall())
    except Exception:
        return []


# ── Rendimiento diario (facturación / clientes / horas / previsión) ─────────────────────────────────
def ventas_por_dia_mes(anio, mes) -> list:
    """[(dia, total, num_tickets)] de ventas del mes (aislado por tenant)."""
    tf, tp = _tenant_filtro()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DAY(fecha), COALESCE(SUM(total),0), COUNT(*) FROM ventas "
                        "WHERE YEAR(fecha)=%s AND MONTH(fecha)=%s" + tf + " GROUP BY DAY(fecha)",
                        (anio, mes, *tp))
            return list(cur.fetchall())
    except Exception:
        return []


def horas_por_dia_mes(anio, mes) -> list:
    """[(dia, minutos_trabajados)] a partir de fichajes cerrados del mes (aislado por tenant)."""
    tf, tp = _tenant_filtro()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DAY(entrada), COALESCE(SUM(TIMESTAMPDIFF(MINUTE, entrada, salida)),0) "
                        "FROM fichajes WHERE salida IS NOT NULL AND YEAR(entrada)=%s AND MONTH(entrada)=%s"
                        + tf + " GROUP BY DAY(entrada)", (anio, mes, *tp))
            return list(cur.fetchall())
    except Exception:
        return []


def rendimiento_diario_guardado(anio, mes) -> list:
    """[(dia, facturacion, clientes, horas, prevision)] guardado (manual) del mes, de la empresa activa."""
    try:
        from src.db.empresa import empresa_actual_id
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DAY(fecha), facturacion, clientes, horas, prevision FROM rendimiento_diario "
                        "WHERE id_empresa=%s AND YEAR(fecha)=%s AND MONTH(fecha)=%s",
                        (empresa_actual_id(), anio, mes))
            return list(cur.fetchall())
    except Exception:
        return []


def guardar_rendimiento_diario(items, id_empresa=None) -> int:
    """Upsert de rendimiento diario. items = iterable de (fecha, facturacion, clientes, horas, prevision)."""
    from src.db.empresa import empresa_actual_id
    eid = id_empresa or empresa_actual_id()
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for fecha, fact, cli, horas, prev in items:
                cur.execute("INSERT INTO rendimiento_diario (id_empresa, fecha, facturacion, clientes, horas, "
                            "prevision) VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                            "facturacion=VALUES(facturacion), clientes=VALUES(clientes), horas=VALUES(horas), "
                            "prevision=VALUES(prevision)", (eid, fecha, fact, cli, horas, prev))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("guardar_rendimiento_diario: %s", e)
    return n
