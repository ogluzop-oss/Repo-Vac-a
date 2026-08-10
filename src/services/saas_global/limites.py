"""
Global SaaS · Límites (Fase VI · Bloque 13). Límites por plan/empresa (usuarios/tiendas/almacenes/
correos/API/plugins/workflow/agentes IA/campañas/almacenamiento) sobre `saas_limites`. Gate de
consumo reutilizando `consumo`. Multiempresa. Sin cobros.
"""

from __future__ import annotations

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("saas_global.limites")

RECURSOS = ("usuarios", "tiendas", "almacenes", "correos", "api", "plugins", "workflow",
            "agentes_ia", "campanas", "almacenamiento_mb")


def fijar_limite(recurso, limite, *, id_empresa=None, plan=None) -> bool:
    if recurso not in RECURSOS:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO saas_limites (id_empresa, plan, recurso, limite) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE limite=VALUES(limite)",
                        (id_empresa, plan, recurso, int(limite)))
            conn.commit()
        return True
    except Exception as e:
        logger.error("fijar_limite: %s", e)
        return False


def sembrar_desde_plan(id_empresa, plan) -> int:
    """Crea los límites de una empresa a partir de los del plan global."""
    from src.services.saas_global import planes_global
    defec = planes_global.LIMITES_DEFECTO.get(plan, {})
    n = 0
    for recurso, limite in defec.items():
        if recurso in RECURSOS and fijar_limite(recurso, limite, id_empresa=id_empresa, plan=plan):
            n += 1
    return n


def limite(recurso, *, id_empresa=None, plan=None) -> int:
    """Límite efectivo (0 = ilimitado). Prioriza el de la empresa; si no, el del plan."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT limite FROM saas_limites WHERE id_empresa=%s AND recurso=%s",
                        (id_empresa, recurso))
            r = cur.fetchone()
            if r is None and plan:
                cur.execute("SELECT limite FROM saas_limites WHERE id_empresa IS NULL AND plan=%s "
                            "AND recurso=%s", (plan, recurso))
                r = cur.fetchone()
        if r is not None:
            return int(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception as e:
        logger.debug("limite: %s", e)
    return 0


def dentro_de_limite(recurso, *, id_empresa=None, plan=None, periodo=None) -> dict:
    """¿El consumo actual está dentro del límite? (0 = ilimitado → siempre dentro)."""
    lim = limite(recurso, id_empresa=id_empresa, plan=plan)
    from src.services.saas_global import consumo
    usado = consumo.consumo_actual(recurso, id_empresa=id_empresa, periodo=periodo)
    dentro = (lim == 0) or (usado < lim)
    return {"recurso": recurso, "limite": lim, "usado": usado, "dentro": dentro,
            "restante": (None if lim == 0 else max(0, lim - usado))}


def resumen(id_empresa=None, *, plan=None, periodo=None) -> dict:
    return {r: dentro_de_limite(r, id_empresa=id_empresa, plan=plan, periodo=periodo)
            for r in RECURSOS}


__all__ = ["RECURSOS", "fijar_limite", "sembrar_desde_plan", "limite", "dentro_de_limite", "resumen"]
