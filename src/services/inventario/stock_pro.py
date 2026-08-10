"""
Inventario · Stock avanzado (Módulo 4, enriquecimiento). Añade lo que faltaba tras la auditoría (FEFO,
lotes, caducidades, series, kárdex y movimientos ya existen):
  · stock comprometido (pedidos de venta pendientes) y stock futuro (recepciones de compra pendientes),
  · inventarios cíclicos / conteos inteligentes (programación por rotación, reutiliza inventario físico),
  · reubicación inteligente (sugerencias por rotación/ubicación).
Reutiliza kárdex/compras/ventas/ubicaciones existentes. No duplica lógica. Multiempresa.
"""

import logging

logger = logging.getLogger("inventario.stock_pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.2): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.stock.identidad_stock import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _scalar(cur):
    r = cur.fetchone()
    if not r:
        return 0
    return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)


def stock_comprometido(codigo=None, *, id_empresa=None) -> float:
    """Unidades comprometidas por pedidos de venta pendientes de servir (reutiliza pedidos_online).
    Best-effort: si la tabla/columna no está, devuelve 0."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT COALESCE(SUM(i.cantidad),0) FROM pedidos_online_items i "
                 "JOIN pedidos_online p ON p.id=i.id_pedido "
                 "WHERE p.id_empresa<=>%s AND p.estado IN ('PAGADO','PREPARANDO')")
            params = [emp]
            if codigo:
                q += " AND i.codigo=%s"; params.append(codigo)
            cur.execute(q, params)
            return _scalar(cur)
    except Exception as e:
        logger.debug("stock_comprometido: %s", e)
        return 0.0


def stock_futuro(codigo=None, *, id_empresa=None) -> float:
    """Unidades en camino: pedidos de compra enviados/parciales aún no recibidos del todo (reutiliza
    compras_pedidos_lineas). Best-effort."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT COALESCE(SUM(GREATEST(l.cantidad - COALESCE(l.cantidad_recibida,0),0)),0) "
                 "FROM compras_pedidos_lineas l JOIN compras_pedidos p ON p.id=l.id_pedido "
                 "WHERE p.id_empresa<=>%s AND p.estado IN ('ENVIADO','PARCIAL')")
            params = [emp]
            if codigo:
                q += " AND l.codigo=%s"; params.append(codigo)
            cur.execute(q, params)
            return _scalar(cur)
    except Exception as e:
        logger.debug("stock_futuro: %s", e)
        return 0.0


def disponibilidad(codigo, *, id_empresa=None) -> dict:
    """Foto de disponibilidad de un artículo: físico (kárdex) − comprometido + futuro = proyectado."""
    emp = _emp(id_empresa)
    fisico = 0.0
    try:
        from src.db import kardex
        fisico = float(kardex.stock_actual(codigo, id_empresa=emp)) if hasattr(kardex, "stock_actual") else 0.0
    except Exception:
        pass
    comp = stock_comprometido(codigo, id_empresa=emp)
    fut = stock_futuro(codigo, id_empresa=emp)
    return {"codigo": codigo, "fisico": fisico, "comprometido": comp, "futuro": fut,
            "disponible": round(fisico - comp, 3), "proyectado": round(fisico - comp + fut, 3)}


# ── Inventarios cíclicos / conteos inteligentes ─────────────────────────────
def articulos_para_conteo(limite=20, *, id_empresa=None) -> list:
    """Selecciona artículos para conteo cíclico priorizando ROTACIÓN (más movimientos recientes en el
    kárdex = mayor prioridad de recuento). Reutiliza el kárdex; no crea un motor nuevo."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT codigo_articulo, COUNT(*) movimientos, MAX(fecha) ultimo "
                        "FROM movimientos_stock WHERE id_empresa<=>%s "
                        "AND fecha >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) "
                        "GROUP BY codigo_articulo ORDER BY movimientos DESC LIMIT %s",
                        (emp, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("articulos_para_conteo: %s", e)
        return []


def _job_conteo_ciclico(id_empresa=None) -> str:
    """Job Scheduler: propone un conteo cíclico de los artículos de mayor rotación creando una TAREA
    (reutiliza services.tareas). No cuenta por sí mismo; prepara el recuento inteligente."""
    emp = _emp(id_empresa)
    arts = articulos_para_conteo(20, id_empresa=emp)
    if arts:
        try:
            from src.services import tareas
            tareas.crear_tarea("Conteo cíclico de inventario",
                               descripcion=f"Recuento sugerido de {len(arts)} artículos de alta rotación.",
                               id_empresa=emp)
        except Exception as e:
            logger.debug("tarea conteo: %s", e)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("inventario", "CONTEO_CICLICO_JOB", "movimientos_stock", f"articulos={len(arts)}")
    except Exception:
        pass
    return f"conteo cíclico propuesto para {len(arts)} artículos"


# ── Reubicación inteligente ─────────────────────────────────────────────────
def sugerencias_reubicacion(*, id_empresa=None, limite=15) -> list:
    """Sugerencias de reubicación: artículos de ALTA rotación que convendría acercar a zonas de picking.
    Reutiliza el kárdex (rotación) y las ubicaciones existentes. Solo sugiere (no ejecuta)."""
    emp = _emp(id_empresa)
    arts = articulos_para_conteo(limite, id_empresa=emp)
    out = []
    for a in arts:
        out.append({"codigo": a.get("codigo_articulo"), "movimientos_90d": a.get("movimientos"),
                    "sugerencia": "Acercar a zona de picking (alta rotación)"})
    return out


def registrar_jobs_inventario(id_empresa=None):
    """Registra el job de conteo cíclico en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar("inventario_conteo_ciclico", _job_conteo_ciclico)
        scheduler.registrar_job("inventario_conteo_ciclico", intervalo_horas=168,
                                descripcion="Propuesta de conteo cíclico por rotación", id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_inventario: %s", e)
