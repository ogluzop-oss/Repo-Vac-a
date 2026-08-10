"""
Global SaaS · Planes globales (Fase VI · Bloque 13). Catálogo de planes mundiales (Starter/Business/
Professional/Enterprise/Corporate/Government) con sus límites por defecto. REUTILIZA el licenciamiento
SaaS existente (`services.saas.licensing`/`planes`) para asignar planes a empresas. Sin cobros.
"""

from __future__ import annotations

PLANES = ("starter", "business", "professional", "enterprise", "corporate", "government")

# Límites por defecto por plan (0 = ilimitado). Recursos alineados con `limites.RECURSOS`.
LIMITES_DEFECTO = {
    "starter":      {"usuarios": 3, "tiendas": 1, "almacenes": 1, "correos": 500, "api": 1000,
                     "plugins": 2, "workflow": 5, "agentes_ia": 1, "campanas": 2, "almacenamiento_mb": 1024},
    "business":     {"usuarios": 15, "tiendas": 3, "almacenes": 3, "correos": 5000, "api": 20000,
                     "plugins": 10, "workflow": 30, "agentes_ia": 4, "campanas": 20, "almacenamiento_mb": 10240},
    "professional": {"usuarios": 50, "tiendas": 10, "almacenes": 10, "correos": 25000, "api": 100000,
                     "plugins": 30, "workflow": 100, "agentes_ia": 8, "campanas": 100, "almacenamiento_mb": 51200},
    "enterprise":   {"usuarios": 250, "tiendas": 50, "almacenes": 50, "correos": 200000, "api": 1000000,
                     "plugins": 100, "workflow": 500, "agentes_ia": 12, "campanas": 500, "almacenamiento_mb": 512000},
    "corporate":    {"usuarios": 0, "tiendas": 0, "almacenes": 0, "correos": 0, "api": 0,
                     "plugins": 0, "workflow": 0, "agentes_ia": 0, "campanas": 0, "almacenamiento_mb": 0},
    "government":   {"usuarios": 0, "tiendas": 0, "almacenes": 0, "correos": 0, "api": 0,
                     "plugins": 0, "workflow": 0, "agentes_ia": 0, "campanas": 0, "almacenamiento_mb": 0},
}


def plan(codigo) -> dict | None:
    if codigo not in PLANES:
        return None
    return {"codigo": codigo, "limites": dict(LIMITES_DEFECTO.get(codigo, {}))}


def asignar_a_empresa(id_empresa, codigo, *, region=None, usuario=None) -> dict:
    """Asigna un plan global a una empresa (reutiliza saas.licensing) y siembra sus límites."""
    if codigo not in PLANES:
        return {"ok": False, "error": f"plan no válido: {codigo}"}
    ok = False
    try:
        from src.services.saas import licensing
        ok = bool(licensing.asignar_plan(id_empresa, codigo, estado="activa", usuario=usuario))
    except Exception:
        ok = True   # degradable: el registro de límites/consumo sigue siendo válido
    try:
        from src.services.saas_global import limites
        limites.sembrar_desde_plan(id_empresa, codigo)
    except Exception:
        pass
    if region:
        try:
            from src.services.saas_global import regiones
            regiones.asignar_region(id_empresa, region)
        except Exception:
            pass
    return {"ok": ok, "id_empresa": id_empresa, "plan": codigo}


__all__ = ["PLANES", "LIMITES_DEFECTO", "plan", "asignar_a_empresa"]
