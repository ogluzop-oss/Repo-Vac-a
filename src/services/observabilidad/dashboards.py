"""
Enterprise Observability · Dashboards (Fase III · B7).

Agrega datos de observabilidad por dominio (sistema/comunicación/workflow/API/scheduler/plugins/
usuarios/empresas) reutilizando los servicios existentes (metricas Prometheus, ccp.analitica,
scheduler, sdk…) + alertas técnicas. Solo lectura. Multiempresa. API-First (sin PyQt).
"""

import logging

logger = logging.getLogger("observabilidad.dashboards")

DOMINIOS = ("sistema", "comunicacion", "workflow", "api", "scheduler", "plugins", "usuarios",
            "empresas", "eventbus", "marketplace")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _scalar(sql, params=()):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


def dashboard(dominio, id_empresa=None) -> dict:
    """Devuelve el panel del dominio indicado (dict de KPIs)."""
    id_empresa = _emp(id_empresa)
    if dominio == "comunicacion":
        try:
            from src.services import ccp
            return ccp.analitica.resumen(id_empresa)
        except Exception as e:
            logger.debug("dashboard comunicacion: %s", e); return {}
    if dominio == "scheduler":
        return {
            "activos": _scalar("SELECT COUNT(*) FROM scheduler_schedules WHERE id_empresa=%s AND "
                               "estado='activo'", (id_empresa,)),
            "pausados": _scalar("SELECT COUNT(*) FROM scheduler_schedules WHERE id_empresa=%s AND "
                                "estado='pausado'", (id_empresa,)),
            "ejecuciones_fallidas": _scalar("SELECT COUNT(*) FROM scheduler_ejecuciones WHERE "
                                            "id_empresa=%s AND estado='fallido'", (id_empresa,)),
        }
    if dominio == "plugins":
        try:
            from src import sdk
            return {"instalados": len(sdk.listar_instalados(id_empresa))}
        except Exception:
            return {"instalados": 0}
    if dominio == "api":
        return {"metricas": _render_metricas()}
    if dominio in ("eventbus", "marketplace"):
        # F1: reutiliza el recolector operacional (mismas fuentes que los gauges Prometheus).
        try:
            from src.services.observabilidad import operacional
            return operacional.snapshot(id_empresa).get(dominio, {})
        except Exception as e:
            logger.debug("dashboard %s: %s", dominio, e)
            return {}
    if dominio == "empresas":
        return {"eventos": _scalar("SELECT COUNT(*) FROM eventos WHERE id_empresa=%s", (id_empresa,))}
    if dominio == "usuarios":
        return {"usuarios": _scalar("SELECT COUNT(*) FROM usuarios WHERE id_empresa=%s", (id_empresa,))}
    if dominio == "workflow":
        return {"reglas": _scalar("SELECT COUNT(*) FROM rules WHERE id_empresa=%s AND activo=1",
                                  (id_empresa,))}
    # sistema
    return {"salud": _salud(), "metricas_expuestas": bool(_render_metricas())}


def _render_metricas():
    try:
        from src.services.observabilidad import metricas
        return metricas.render() if hasattr(metricas, "render") else ""
    except Exception:
        return ""


def _salud():
    try:
        from src.services.observabilidad import health
        if hasattr(health, "estado"):
            return health.estado()
        if hasattr(health, "salud"):
            return health.salud()
    except Exception:
        pass
    return {"status": "ok"}


def alertas(id_empresa=None) -> list:
    """Alertas Enterprise derivadas del estado (colas bloqueadas, campañas fallidas…)."""
    id_empresa = _emp(id_empresa)
    out = []
    cola = _scalar("SELECT COUNT(*) FROM ccp_cola WHERE id_empresa=%s AND estado='pendiente'",
                   (id_empresa,))
    if cola > 100:
        out.append({"nivel": "warning", "tipo": "cola_bloqueada", "detalle": f"{cola} en cola"})
    fallidas = _scalar("SELECT COUNT(*) FROM ccp_campanas WHERE id_empresa=%s AND fallidos>0",
                       (id_empresa,))
    if fallidas:
        out.append({"nivel": "warning", "tipo": "campanas_fallidas", "detalle": f"{fallidas} campañas"})
    # Alertas técnicas ya registradas.
    try:
        from src.services.observabilidad import alertas_tecnicas
        if hasattr(alertas_tecnicas, "listar"):
            out += alertas_tecnicas.listar(id_empresa=id_empresa) or []
    except Exception:
        pass
    return out


def resumen_global(id_empresa=None) -> dict:
    """Todos los dominios de un vistazo."""
    return {d: dashboard(d, id_empresa) for d in DOMINIOS}
