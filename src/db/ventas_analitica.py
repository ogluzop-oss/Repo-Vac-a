"""Capa de datos de la ANALÍTICA de ventas (dashboard `gui/ventas`): histórico de previsión,
objetivos anuales, series de ventas del TPV, top de artículos y rendimiento diario.

Fase 3 · cliente fino: extraído de `gui/ventas` para que la ventana no ejecute SQL directo. La GUI
solo orquesta (gráficas, tablas, IA); aquí viven las consultas/escrituras y el filtro de tenant.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("ventas.analitica")


def _tenant_filtro(alias=None):
    """Fragmento WHERE + params para aislar por empresa/tienda ACTIVAS. `alias` = prefijo de tabla."""
    from src.db.empresa import empresa_actual_id, tienda_actual_id_int
    p = f"{alias}." if alias else ""
    frag = f" AND {p}id_empresa=%s"
    params = [empresa_actual_id()]
    tid = tienda_actual_id_int()
    if tid is not None:
        frag += f" AND {p}id_tienda=%s"
        params.append(tid)
    return frag, params


# ── Histórico de previsión ────────────────────────────────────────────────────────────────────────
def importar_prevision_historico(items) -> int:
    """Upsert de histórico: items = iterable de (fecha, total_facturado, dia_semana)."""
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for fecha, total, dia in items:
                cur.execute("INSERT INTO prevision_historico (fecha, total_facturado, fuente, dia_semana) "
                            "VALUES (%s,%s,'IMPORTADO',%s) ON DUPLICATE KEY UPDATE "
                            "total_facturado=VALUES(total_facturado), dia_semana=VALUES(dia_semana)",
                            (fecha, total, dia))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("importar_prevision_historico: %s", e)
    return n


def resumen_historico() -> list:
    """[(anio, dias, total, fuente)] agrupado por año y fuente."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT YEAR(fecha) AS anio, COUNT(*) AS dias, SUM(total_facturado) AS total, fuente "
                        "FROM prevision_historico GROUP BY anio, fuente ORDER BY anio DESC, fuente")
            return list(cur.fetchall())
    except Exception:
        return []


def contar_historico() -> int:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prevision_historico")
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


def serie_historico() -> list:
    """[(fecha, total_facturado)] ordenado por fecha (una fila por registro)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fecha, total_facturado FROM prevision_historico ORDER BY fecha")
            return list(cur.fetchall())
    except Exception:
        return []


def serie_historico_agrupada() -> list:
    """[(fecha, SUM(total_facturado))] agrupado por fecha (para la IA predictiva)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fecha, SUM(total_facturado) FROM prevision_historico "
                        "GROUP BY fecha ORDER BY fecha")
            return list(cur.fetchall())
    except Exception:
        return []


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
def serie_por_dia(desde, hasta, art=None, secc=None) -> list:
    """[(dia, total)] de ventas por día entre `desde` y `hasta`; opcional por artículo o sección."""
    tf, tp = _tenant_filtro("v")
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


def top_articulos(desde, hasta, secc=None, limite=10) -> list:
    """[(codigo, nombre, uds)] de los artículos más vendidos en el rango; opcional por sección."""
    tf, tp = _tenant_filtro("v")
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
