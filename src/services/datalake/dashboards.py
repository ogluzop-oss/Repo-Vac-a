"""
Data Lake · Dashboards (Fase V · Bloque 6). Catálogo de dashboards de BI empresarial servidos desde
el lago/DW (reutiliza `bi`/`bi_corp`). Cada dashboard es un descriptor (dominio + KPIs) que se
alimenta de `lake.consultar` — nunca de SQL propio. Multiempresa.
"""

from __future__ import annotations

from src.services.datalake import lake

# Dashboard → dominio del lago.
DASHBOARDS = {
    "ventas": "ventas", "compras": "compras", "stock": "stock", "rrhh": "rrhh",
    "produccion": "produccion", "calidad": "calidad", "finanzas": "finanzas",
    "logistica": "logistica", "ccp": "ccp", "workflow": "workflow", "api": "api",
    "usuarios": "usuarios", "empresas": "empresas",
}


def listar() -> list:
    return sorted(DASHBOARDS.keys())


def dashboard(nombre, *, id_empresa=None, granularidad="mensual", periodo=None) -> dict:
    """Datos de un dashboard (KPIs del dominio, desde el DW). Degradable a vacío."""
    dominio = DASHBOARDS.get(nombre)
    if not dominio:
        return {"ok": False, "error": "dashboard desconocido"}
    datos = lake.consultar(dominio=dominio, granularidad=granularidad, periodo=periodo,
                           id_empresa=id_empresa)
    return {"ok": True, "dashboard": nombre, "dominio": dominio,
            "kpis": datos if isinstance(datos, list) else [], "granularidad": granularidad}


def descriptor() -> dict:
    return {"dashboards": listar(), "fuente": "datalake/bi_corp.dw"}


__all__ = ["DASHBOARDS", "listar", "dashboard", "descriptor"]
