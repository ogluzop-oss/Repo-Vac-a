"""
Analítica — métricas por publicación (sincronizadas desde la plataforma) + cruce con el ERP
(ventas/presupuestos del MISMO rango de fechas, vía `db.ventas_analitica.resumen_periodo` y la
tabla `ventas_presupuestos` ya existentes, reutilizadas sin duplicar). Honestidad de alcance: no
existe ningún identificador de campaña/UTM que ligue una venta concreta a una publicación
concreta, así que el cruce es CORRELACIÓN TEMPORAL (actividad social vs. ERP en el mismo periodo),
nunca "atribución" exacta — se etiqueta así en todos los resultados para no inducir a error.
"""

import logging

logger = logging.getLogger("redes_sociales.analitica")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def registrar_metricas(id_publicacion, *, impresiones=0, alcance=0, interacciones=0, likes=0,
                       comentarios=0, compartidos=0, clics=0) -> dict:
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO redes_sociales_metricas (id_publicacion, impresiones, alcance, "
                "interacciones, likes, comentarios, compartidos, clics) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_publicacion, int(impresiones or 0), int(alcance or 0), int(interacciones or 0),
                 int(likes or 0), int(comentarios or 0), int(compartidos or 0), int(clics or 0)))
        return {"ok": True}
    except Exception as e:
        logger.error("registrar_metricas(%s): %s", id_publicacion, e)
        return {"ok": False, "error": "error_interno"}


def sincronizar_metricas(id_publicacion, id_empresa=None) -> dict:
    """Pide a la plataforma las métricas reales de una publicación ya publicada y las persiste.
    Normalización best-effort (cada plataforma nombra sus campos distinto); si la plataforma no
    expone insights (p. ej. YouTube no detalla por comentario), degrada honestamente."""
    from src.services.redes_sociales import calendario as _cal
    from src.services.redes_sociales import cuentas as _cuentas
    from src.services.redes_sociales.plataformas import cliente_para

    id_empresa = _emp(id_empresa)
    pubs = _cal.listar_publicaciones(id_empresa=id_empresa, limite=100000)
    pub = next((p for p in pubs if p["id"] == id_publicacion), None)
    if not pub or pub["estado"] != "publicada" or not pub.get("externo_id"):
        return {"ok": False, "estado": "publicacion_no_publicada"}
    cli = cliente_para(pub["plataforma"])
    if cli is None or not hasattr(cli, "obtener_metricas"):
        return {"ok": False, "estado": "no_disponible_en_la_plataforma"}
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == pub["id_cuenta"]), None)
    if not cuenta:
        return {"ok": False, "estado": "cuenta_no_encontrada"}

    r = cli.obtener_metricas(pub["id_cuenta"], pub["externo_id"], id_empresa=id_empresa)
    if not r.get("ok"):
        return r
    bruto = r.get("metricas")
    campos = {"impresiones": 0, "alcance": 0, "interacciones": 0, "likes": 0, "comentarios": 0,
             "compartidos": 0, "clics": 0}
    if isinstance(bruto, dict):
        campos["likes"] = int(bruto.get("like_count") or bruto.get("likeCount") or 0)
        campos["comentarios"] = int(bruto.get("comment_count") or bruto.get("commentCount") or 0)
        campos["compartidos"] = int(bruto.get("share_count") or bruto.get("retweet_count") or 0)
        campos["alcance"] = int(bruto.get("view_count") or bruto.get("viewCount") or
                                bruto.get("impression_count") or 0)
    registrar_metricas(id_publicacion, **campos)
    return {"ok": True, "metricas": campos}


def resumen_publicaciones(*, desde=None, hasta=None, plataforma=None, id_empresa=None) -> dict:
    """Agregado de métricas de publicaciones del rango — alimenta los informes ejecutivos."""
    id_empresa = _emp(id_empresa)
    filtros, params = ["p.id_empresa=%s"], [id_empresa]
    if plataforma:
        filtros.append("p.plataforma=%s"); params.append(plataforma)
    if desde:
        filtros.append("p.fecha_publicada >= %s"); params.append(desde)
    if hasta:
        filtros.append("p.fecha_publicada <= %s"); params.append(hasta)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.plataforma, COUNT(DISTINCT p.id), "
                "COALESCE(SUM(m.impresiones),0), COALESCE(SUM(m.alcance),0), "
                "COALESCE(SUM(m.interacciones),0), COALESCE(SUM(m.likes),0), "
                "COALESCE(SUM(m.comentarios),0), COALESCE(SUM(m.compartidos),0), "
                "COALESCE(SUM(m.clics),0) FROM redes_sociales_publicaciones p "
                "LEFT JOIN redes_sociales_metricas m ON m.id_publicacion=p.id "
                "WHERE " + " AND ".join(filtros) + " AND p.estado='publicada' "
                "GROUP BY p.plataforma", params)
            filas = cur.fetchall()
    except Exception as e:
        logger.error("resumen_publicaciones: %s", e)
        return {"ok": False, "error": "error_interno"}
    por_plataforma = [
        {"plataforma": f[0], "publicaciones": f[1], "impresiones": f[2], "alcance": f[3],
         "interacciones": f[4], "likes": f[5], "comentarios": f[6], "compartidos": f[7],
         "clics": f[8]} for f in filas]
    return {"ok": True, "por_plataforma": por_plataforma}


def cruce_con_ventas(desde, hasta, *, id_empresa=None) -> dict:
    """Correlación temporal (NO atribución exacta, ver docstring del módulo): actividad social del
    rango vs. `ventas_analitica.resumen_periodo` (facturación/tickets reales) y nº de presupuestos
    (`ventas_presupuestos`) creados en el mismo rango — ambos motores YA existentes, reutilizados."""
    id_empresa = _emp(id_empresa)
    social = resumen_publicaciones(desde=desde, hasta=hasta, id_empresa=id_empresa)

    try:
        from src.db.ventas_analitica import resumen_periodo
        ventas = resumen_periodo(desde, hasta, id_empresa=id_empresa)
    except Exception as e:
        logger.error("cruce_con_ventas: resumen_periodo: %s", e)
        ventas = {}

    n_presupuestos = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ventas_presupuestos WHERE id_empresa=%s AND "
                "DATE(fecha) BETWEEN %s AND %s", (id_empresa, desde, hasta))
            fila = cur.fetchone()
            n_presupuestos = int(fila[0] or 0) if fila else 0
    except Exception as e:
        logger.debug("cruce_con_ventas: ventas_presupuestos no disponible: %s", e)

    return {"ok": True, "aviso": "Correlación temporal (mismo rango de fechas), NO atribución "
                                "exacta: no existe un identificador de campaña/UTM que ligue una "
                                "venta concreta a una publicación concreta.",
           "desde": desde, "hasta": hasta, "actividad_social": social.get("por_plataforma", []),
           "ventas_erp": ventas, "presupuestos_creados": n_presupuestos}
