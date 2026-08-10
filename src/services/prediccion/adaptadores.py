"""
Adaptadores de LECTURA del motor predictivo (Paquete Enterprise 3). REUTILIZA el adaptador
read-only de la IA (`ia.adaptadores`) para no duplicar consultas, y añade unas pocas lecturas
propias de prediccion (rotacion, clientes por actividad, vencimientos). Solo lee; nunca escribe.
"""

import logging

from src.services.ia import adaptadores as _IAA

logger = logging.getLogger("prediccion.adaptadores")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _q(sql, params=(), id_empresa=None):
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("consulta prediccion: %s", e)
        return []


# ── Reutilizacion directa del adaptador de IA (no se duplica logica) ──────────
ventas_por_dia = _IAA.ventas_por_dia
articulos_bajo_umbral = _IAA.articulos_bajo_umbral
articulos_exceso = _IAA.articulos_exceso
mermas_recientes = _IAA.mermas_recientes
facturas_pendientes = _IAA.facturas_pendientes
contratos_por_vencer = _IAA.contratos_por_vencer
kpis = _IAA.kpis
sincronizacion = _IAA.sincronizacion


# ── Lecturas propias de prediccion (best-effort) ──────────────────────────────
def rotacion_articulos(id_empresa=None, *, dias=30, limite=20) -> list:
    """Articulos mas vendidos en el periodo (alta rotacion)."""
    emp = _emp(id_empresa)
    return _q("SELECT vi.codigo_articulo codigo, COALESCE(SUM(vi.cantidad),0) uds "
              "FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
              "WHERE v.id_empresa=%s AND v.fecha >= (NOW() - INTERVAL %s DAY) "
              "GROUP BY vi.codigo_articulo ORDER BY uds DESC LIMIT %s",
              (emp, int(dias), int(limite)), id_empresa=emp)


def ventas_hist_por_dia(id_empresa=None, *, dias=180) -> list:
    """Serie diaria del HISTÓRICO IMPORTADO (`ventas_historicas`) — ventas anteriores a Smart Manager cargadas
    para el forecasting. Aislada por empresa. No es la tabla operativa `ventas` (no afecta a finanzas)."""
    emp = _emp(id_empresa)
    return _q("SELECT fecha d, COALESCE(SUM(importe),0) total FROM ventas_historicas "
              "WHERE id_empresa=%s AND fecha >= (CURDATE() - INTERVAL %s DAY) "
              "GROUP BY fecha ORDER BY fecha", (emp, int(dias)), id_empresa=emp)


def sin_movimiento(id_empresa=None, *, dias=60, limite=50) -> list:
    """Articulos con stock pero SIN ventas en el periodo (producto parado)."""
    emp = _emp(id_empresa)
    return _q("SELECT a.codigo, a.nombre FROM articulos a WHERE COALESCE(a.Stock_total,0)>0 "
              "AND a.codigo NOT IN (SELECT DISTINCT vi.codigo_articulo FROM venta_items vi "
              "JOIN ventas v ON v.id=vi.venta_id WHERE v.id_empresa=%s "
              "AND v.fecha >= (NOW() - INTERVAL %s DAY)) LIMIT %s",
              (emp, int(dias), int(limite)), id_empresa=emp)


def clientes_por_actividad(id_empresa=None, *, dias=90, limite=100) -> list:
    """Ventas por cliente en el periodo (para detectar inactivos/crecimiento)."""
    emp = _emp(id_empresa)
    return _q("SELECT cliente_id, cliente_nombre, COUNT(*) tickets, COALESCE(SUM(total),0) importe, "
              "MAX(fecha) ultima FROM ventas WHERE id_empresa=%s AND cliente_id IS NOT NULL "
              "AND fecha >= (NOW() - INTERVAL %s DAY) GROUP BY cliente_id ORDER BY importe DESC LIMIT %s",
              (emp, int(dias), int(limite)), id_empresa=emp)
