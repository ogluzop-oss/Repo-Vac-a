"""
Fase Productividad · Facturación EN VIVO por centro y por empleado.

Nunca se cachea ni se recalcula por cron: cada consulta suma `ventas.total` directamente para el
rango de fechas pedido (actual o histórico) — mismo criterio ya aplicado en el resto de la app
(p.ej. `facturas_cliente.informe_margenes`). El cableado real viene de la migración 0294
(`ventas.id_tienda`/`ventas.id_usuario`, poblados por la ruta canónica `registrar_venta_con_items`
desde el TPV) — antes de esa migración no existía una atribución fiable por empleado.
"""

from src.db.conexion import obtener_conexion


def facturado_centro(id_tienda, fecha_desde, fecha_hasta, id_empresa) -> float:
    """Total facturado por un centro (identificado por su `id_tienda` operativo real) en
    [fecha_desde, fecha_hasta] (inclusive)."""
    if id_tienda is None:
        return 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(total),0) FROM ventas WHERE id_empresa=%s AND id_tienda=%s "
                "AND DATE(fecha) BETWEEN %s AND %s",
                (id_empresa, id_tienda, fecha_desde, fecha_hasta))
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0.0


def facturado_empleado(usuario_id, fecha_desde, fecha_hasta, id_empresa) -> float:
    """Total facturado por UN empleado (vía `ventas.id_usuario`, fiable desde la migración 0294)
    en [fecha_desde, fecha_hasta] (inclusive). Ventas anteriores a esa migración (`id_usuario`
    NULL) nunca se atribuyen retroactivamente — quedan honestamente fuera de este total."""
    if usuario_id is None:
        return 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(total),0) FROM ventas WHERE id_empresa=%s AND id_usuario=%s "
                "AND DATE(fecha) BETWEEN %s AND %s",
                (id_empresa, usuario_id, fecha_desde, fecha_hasta))
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0.0
