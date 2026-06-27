"""
Métricas SaaS (FASE SAAS-L): empresas/usuarios activos, MRR, ARR, churn.
Reutiliza planes_saas (precios) y empresa_licencia/suscripciones.
"""

import logging
from src.db.conexion import obtener_conexion

logger = logging.getLogger("saas.metricas")


def _scalar(sql, params=()):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.debug("scalar: %s", e)
        return 0.0


def resumen() -> dict:
    """Métricas globales del SaaS (uso SUPERADMIN/operador de plataforma)."""
    empresas_activas = int(_scalar("SELECT COUNT(*) FROM empresa_licencia WHERE estado IN ('activa','prueba')"))
    canceladas = int(_scalar("SELECT COUNT(*) FROM empresa_licencia WHERE estado='cancelada'"))
    total = int(_scalar("SELECT COUNT(*) FROM empresa_licencia"))
    usuarios_activos = int(_scalar("SELECT COUNT(*) FROM usuarios WHERE activo=1"))
    # MRR: suma del precio mensual del plan de cada suscripción activa.
    mrr = _scalar("SELECT COALESCE(SUM(p.precio_mensual),0) FROM suscripciones s "
                  "JOIN planes_saas p ON p.codigo=s.codigo_plan WHERE s.estado='activa'")
    churn = round((canceladas / total * 100), 2) if total else 0.0
    return {"empresas_activas": empresas_activas, "empresas_canceladas": canceladas,
            "empresas_total": total, "usuarios_activos": usuarios_activos,
            "mrr": round(mrr, 2), "arr": round(mrr * 12, 2), "churn_pct": churn}


def consumo_empresa(id_empresa) -> dict:
    """Consumo de una empresa (para portal cliente / panel tenants)."""
    def c(tabla):
        return int(_scalar(f"SELECT COUNT(*) FROM {tabla} WHERE id_empresa=%s", (id_empresa,)))
    return {"usuarios": c("usuarios"), "ventas": c("ventas"),
            "documentos": c("documentos_registro"), "notificaciones": c("notificaciones"),
            "workflow_instancias": c("wf_instancias")}
