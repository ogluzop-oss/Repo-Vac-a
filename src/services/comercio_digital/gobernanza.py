"""
PCD · Gobernanza transversal (Fase 9). Punto ÚNICO de integración de la Plataforma de Comercio Digital
con las capacidades Enterprise de gobierno: RBAC, SaaS (límites/feature flags), CCP (comunicaciones) y
Observabilidad (métricas/salud).

NO es un motor ni introduce conceptos nuevos: solo CABLEA capacidades (N7/Regla 6). Todo degradable:
si una capacidad no está disponible, se degrada con elegancia sin romper el comportamiento existente
(RBAC → permitido legacy; SaaS → permitido; CCP → no registra; métricas → no-op).
"""

from __future__ import annotations

import logging

from src.platform import capabilities as cap

logger = logging.getLogger("cd.gobernanza")

FASE = 9

# Permisos que CONSUME la PCD (se resuelven vía RBAC Enterprise; la PCD no define roles/ACL).
# Alineados con el catálogo canónico RBAC (`seguridad.catalogo.CATALOGO`, C0.P1). No es un segundo
# sistema de permisos: son las CLAVES que la PCD pasa a `rbac.puede()`.
PERMISOS = ("comercio.ver", "comercio.admin", "comercio.transaccion", "comercio.checkout",
            "comercio.catalogo", "comercio.publicaciones", "comercio.presencia",
            "comercio.canales", "comercio.conexiones", "comercio.sync", "comercio.marketplaces",
            "comercio.pagos", "comercio.logistica",
            "comercio.campanas", "comercio.feeds", "comercio.automatizacion")


class PermisoDenegado(Exception):
    """Se lanza al exigir un permiso no concedido (delegado en RBAC)."""


# ── RBAC ──────────────────────────────────────────────────────────────────────
def puede(usuario, permiso, *, id_empresa=None) -> bool:
    """¿`usuario` tiene `permiso`? Delega en RBAC (capacidad). Degradable/legacy-safe → True."""
    try:
        rbac = cap.rbac()
        if rbac is not None and hasattr(rbac, "puede"):
            return bool(rbac.puede(usuario, permiso, id_empresa=id_empresa))
    except Exception as e:
        logger.debug("RBAC no disponible (%s): %s", permiso, e)
    return True


def exigir(usuario, permiso, *, id_empresa=None):
    if not puede(usuario, permiso, id_empresa=id_empresa):
        raise PermisoDenegado(permiso)
    return True


# ── SaaS (límites / feature flags) ────────────────────────────────────────────
def feature_activa(flag, *, id_empresa=None) -> bool:
    """¿La feature está activa para el plan/tenant? Delega en SaaS. Degradable → True."""
    try:
        saas = cap.saas_global()
        ff = getattr(saas, "feature_flags", None)
        if ff is not None and hasattr(ff, "activo"):
            return bool(ff.activo(flag, id_empresa=id_empresa))
    except Exception as e:
        logger.debug("SaaS feature_flags no disponible (%s): %s", flag, e)
    return True


def dentro_de_limite(recurso, *, id_empresa=None) -> bool:
    """¿El tenant está dentro del límite del plan para `recurso`? Delega en SaaS. Degradable → True."""
    try:
        saas = cap.saas_global()
        lim = getattr(saas, "limites", None)
        if lim is not None and hasattr(lim, "dentro_de_limite"):
            r = lim.dentro_de_limite(recurso, id_empresa=id_empresa)
            if isinstance(r, dict):
                for k in ("permitido", "dentro", "ok"):
                    if k in r:
                        return bool(r[k])
                return True
            return bool(r)
    except Exception as e:
        logger.debug("SaaS limites no disponible (%s): %s", recurso, e)
    return True


# ── CCP (comunicaciones de comercio) ──────────────────────────────────────────
def notificar_cliente(tipo, *, id_empresa=None, com_id=None, canal="comercio", estado=None) -> bool:
    """Registra una comunicación de comercio en la CCP (capacidad). NO envía correos duplicados: usa
    el registro de eventos de comunicación. Degradable/no bloqueante → False si no hay CCP."""
    try:
        ccp = cap.ccp()
        if ccp is not None and hasattr(ccp, "registrar_evento"):
            ccp.registrar_evento(tipo, id_empresa=id_empresa, com_id=com_id, canal=canal,
                                 estado=estado)
            return True
    except Exception as e:
        logger.debug("CCP no disponible (%s): %s", tipo, e)
    return False


# ── Observabilidad ────────────────────────────────────────────────────────────
def metrica(nombre, valor=1, *, etiqueta=None) -> bool:
    """Incrementa una métrica en Observabilidad (capacidad). Degradable/no-op."""
    try:
        obs = cap.observabilidad()
        met = getattr(obs, "metricas", None)
        if met is None and obs is not None:
            import importlib
            met = importlib.import_module("src.services.observabilidad.metricas")
        if met is not None and hasattr(met, "inc"):
            met.inc(nombre, valor, etiqueta)
            return True
    except Exception as e:
        logger.debug("métrica no disponible (%s): %s", nombre, e)
    return False


def _cap_estado() -> dict:
    return {n: cap.disponible(n) for n in ("rbac", "saas_global", "ccp", "observabilidad",
                                           "eventbus", "workflow", "ia")}


def salud() -> dict:
    """Health de la PCD para el Service Registry (reutiliza el descriptor + estado de capacidades)."""
    try:
        from src.services import comercio_digital as cd
        d = cd.descriptor()
        return {"status": "ok", "fase": d.get("fase"), "estado": d.get("estado"),
                "capacidades": _cap_estado()}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


def descriptor() -> dict:
    return {"servicio": "cd_gobernanza", "fase": FASE, "estado": "implementado", "es_motor": False,
            "permisos": list(PERMISOS), "reutiliza": ["rbac", "saas_global", "ccp", "observabilidad"],
            "capacidades_disponibles": _cap_estado()}


__all__ = ["FASE", "PERMISOS", "PermisoDenegado", "puede", "exigir", "feature_activa",
           "dentro_de_limite", "notificar_cliente", "metrica", "salud", "descriptor"]
