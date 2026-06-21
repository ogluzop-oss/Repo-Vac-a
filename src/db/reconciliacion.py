"""
Reconciliación de integridad (M3) — diagnóstico y reparación controlada.

Los hooks de inventario/contabilidad/fiscalidad se ejecutan best-effort tras el commit; si
el proceso cae, pueden quedar divergencias. Este módulo NO repara automáticamente: primero
DETECTA e INFORMA; la reparación es explícita y solo aplica operaciones seguras (reseed del
ledger desde la caché, reproceso de la cola contable). Multiempresa. Sin Qt.

Uso típico:
    from src.db import reconciliacion
    rep = reconciliacion.diagnostico()          # solo lectura
    reconciliacion.reparar(rep, aplicar=True)   # reparación controlada
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("inventario.reconciliacion")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


# ── Detección ────────────────────────────────────────────────────────────────
def divergencias_stock(id_empresa=None) -> list:
    """Artículos gestionados donde Σ(stock_almacen no-tienda) ≠ articulos.Stock_total
    o Σ(central) ≠ articulos.Stock_central (caché derivada desincronizada del ledger)."""
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT a.codigo,
                       COALESCE(a.Stock_central,0) AS cache_central,
                       COALESCE(a.Stock_total,0)   AS cache_total,
                       COALESCE(SUM(CASE WHEN al.tipo_almacen='central' THEN s.cantidad END),0) AS led_central,
                       COALESCE(SUM(CASE WHEN al.tipo_almacen<>'tienda' THEN s.cantidad END),0) AS led_total
                FROM articulos a
                JOIN stock_almacen s ON s.codigo_articulo=a.codigo AND s.id_empresa=a.id_empresa
                JOIN almacen al ON al.id=s.id_almacen
                WHERE a.id_empresa=%s
                GROUP BY a.codigo, a.Stock_central, a.Stock_total
                HAVING cache_central<>led_central OR cache_total<>led_total
            """, (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("divergencias_stock: %s", e); return []


def movimientos_sin_documento(id_empresa=None, limite=500) -> list:
    """Movimientos de stock huérfanos (sin documento ni palé) — posibles incompletos."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, codigo_articulo, tipo_movimiento, cantidad, fecha_movimiento "
                        "FROM movimientos_stock WHERE id_empresa=%s AND (id_documento IS NULL OR "
                        "id_documento='') AND (id_pale IS NULL OR id_pale='') "
                        "ORDER BY id DESC LIMIT %s", (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("movimientos_sin_documento: %s", e); return []


def cola_contable_pendiente(id_empresa=None, dias_antiguedad=1) -> dict:
    """Eventos contables pendientes (y los 'antiguos' = riesgo de asientos no generados)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM contab_cola WHERE id_empresa=%s AND estado='pendiente'",
                        (id_empresa,))
            pend = cur.fetchone(); pend = (pend[0] if not isinstance(pend, dict) else list(pend.values())[0]) or 0
            cur.execute("SELECT COUNT(*) FROM contab_cola WHERE id_empresa=%s AND estado='pendiente' "
                        "AND fecha < (NOW() - INTERVAL %s DAY)", (id_empresa, int(dias_antiguedad)))
            ant = cur.fetchone(); ant = (ant[0] if not isinstance(ant, dict) else list(ant.values())[0]) or 0
        return {"pendientes": pend, "antiguos": ant}
    except Exception as e:
        logger.error("cola_contable_pendiente: %s", e); return {"pendientes": 0, "antiguos": 0}


def cola_fiscal_pendiente(id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fiscal_cola WHERE id_empresa=%s AND estado<>'hecho'",
                        (id_empresa,))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.error("cola_fiscal_pendiente: %s", e); return 0


def diagnostico(id_empresa=None) -> dict:
    """Informe global de integridad (solo lectura)."""
    id_empresa = _emp(id_empresa)
    div = divergencias_stock(id_empresa)
    cc = cola_contable_pendiente(id_empresa)
    return {
        "id_empresa": id_empresa,
        "divergencias_stock": div,
        "n_divergencias_stock": len(div),
        "movimientos_huerfanos": len(movimientos_sin_documento(id_empresa)),
        "cola_contable": cc,
        "cola_fiscal_pendiente": cola_fiscal_pendiente(id_empresa),
        "ok": (not div and cc["antiguos"] == 0),
    }


# ── Reparación controlada ─────────────────────────────────────────────────────
def reparar(rep: dict = None, aplicar: bool = False, id_empresa=None) -> dict:
    """Reparación SEGURA: (1) re-siembra el ledger desde la caché para los artículos con
    divergencia (stock_almacen ← articulos.Stock_*); (2) reprocesa la cola contable. Con
    `aplicar=False` (defecto) solo simula e informa. No borra ni sobrescribe históricos."""
    id_empresa = _emp(id_empresa)
    rep = rep or diagnostico(id_empresa)
    acciones = {"stock_reseed": [], "cola_procesada": None, "aplicado": bool(aplicar)}
    if not aplicar:
        acciones["plan"] = {
            "reseed_articulos": [d["codigo"] for d in rep.get("divergencias_stock", [])],
            "reprocesar_cola": rep.get("cola_contable", {}).get("pendientes", 0),
        }
        return acciones
    # (1) Reseed del ledger desde la caché (operación idempotente de INV.4).
    try:
        from src.db import stock_almacen as SA
        for d in rep.get("divergencias_stock", []):
            if SA.reseed_articulo(d["codigo"], id_empresa):
                acciones["stock_reseed"].append(d["codigo"])
    except Exception as e:
        logger.error("reparar/reseed: %s", e)
    # (2) Reproceso de la cola contable (idempotente tras M1).
    try:
        from src.services.contabilidad import posting
        acciones["cola_procesada"] = posting.procesar_cola(id_empresa)
    except Exception as e:
        logger.error("reparar/cola: %s", e)
    return acciones
