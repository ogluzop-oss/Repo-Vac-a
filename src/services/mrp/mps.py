"""
Plan Maestro de Producción — MPS (Módulo 15, enriquecimiento de MRP). Genuinamente ausente.
Consolida la demanda por periodo/artículo (pedidos de cliente + previsión) y la entrega al
planificador de necesidades existente (`mrp.planificador.calcular_necesidades/generar_sugerencias`),
que NO se reimplementa. Multiempresa, auditado. No duplica.
"""

import logging

logger = logging.getLogger("mrp.mps")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.4): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.produccion.identidad_produccion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="mrp_plan_maestro"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("mrp", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def fijar_linea_mps(periodo, articulo, *, demanda_pedidos=0, demanda_prevision=0, plan_produccion=None,
                    id_empresa=None) -> int | None:
    """Fija/actualiza una línea del plan maestro (periodo YYYY-MM, artículo). El plan de producción
    por defecto iguala la demanda total si no se especifica."""
    emp = _emp(id_empresa)
    dp = round(float(demanda_pedidos or 0), 3)
    dpv = round(float(demanda_prevision or 0), 3)
    total = round(dp + dpv, 3)
    plan = round(float(plan_produccion), 3) if plan_produccion is not None else total
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO mrp_plan_maestro (id_empresa, periodo, articulo, demanda_pedidos, "
                        "demanda_prevision, demanda_total, plan_produccion) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE demanda_pedidos=VALUES(demanda_pedidos), "
                        "demanda_prevision=VALUES(demanda_prevision), demanda_total=VALUES(demanda_total), "
                        "plan_produccion=VALUES(plan_produccion), actualizado=NOW()",
                        (emp, periodo, str(articulo), dp, dpv, total, plan))
            mid = cur.lastrowid
            c.commit()
        _audit("MPS_LINEA", f"{periodo}/{articulo} total{total} plan{plan}")
        return mid
    except Exception as e:
        logger.error("fijar_linea_mps: %s", e)
        return None


def plan_maestro(periodo, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM mrp_plan_maestro WHERE id_empresa<=>%s AND periodo=%s "
                        "ORDER BY articulo", (emp, periodo))
            return _filas(cur)
    except Exception as e:
        logger.error("plan_maestro: %s", e)
        return []


def confirmar_periodo(periodo, *, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE mrp_plan_maestro SET estado='CONFIRMADO', actualizado=NOW() "
                        "WHERE id_empresa<=>%s AND periodo=%s", (emp, periodo))
            c.commit()
        _audit("MPS_CONFIRMADO", periodo)
        return {"ok": True}
    except Exception as e:
        logger.error("confirmar_periodo: %s", e)
        return {"ok": False, "motivo": str(e)}


def lanzar_mrp(periodo, *, persistir=True, id_empresa=None) -> dict:
    """Toma el plan maestro del periodo y lo entrega al planificador existente para calcular
    necesidades netas y sugerencias de compra/fabricación. REUTILIZA `mrp.planificador`."""
    emp = _emp(id_empresa)
    lineas = plan_maestro(periodo, id_empresa=emp)
    demanda = {str(l["articulo"]): float(l["plan_produccion"] or 0) for l in lineas
               if float(l.get("plan_produccion") or 0) > 0}
    if not demanda:
        return {"ok": False, "motivo": "plan maestro vacío", "demanda": {}}
    try:
        from src.services.mrp import planificador
        res = planificador.generar_sugerencias(demanda, persistir=persistir, id_empresa=emp)
        _audit("MPS_LANZADO", f"{periodo}:{len(demanda)} art")
        return {"ok": True, "demanda": demanda, **(res or {})}
    except Exception as e:
        logger.error("lanzar_mrp: %s", e)
        return {"ok": False, "motivo": str(e), "demanda": demanda}
