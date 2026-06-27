"""
Dashboard BI + comparativas multiempresa + exportación (FASE BI-12/13/17).

Compone el cuadro de mando (secciones por dominio) reutilizando el motor de KPIs, ofrece
comparativas entre empresas/periodos (solo SUPERADMIN, respetando TenantContext: cada empresa
se calcula con su propio id_empresa, sin romper aislamiento) y exporta a JSON/CSV.
"""

import csv
import io
import json
import logging

from src.services.bi import kpis as _K

logger = logging.getLogger("bi.dashboard")


def panel(id_empresa=None, *, periodo="mes", fecha=None, con_forecast=False) -> dict:
    """Cuadro de mando de una empresa. Audita la apertura."""
    _gate("bi", id_empresa)
    d = _K.obtener_dashboard(id_empresa, periodo=periodo, fecha=fecha)
    if con_forecast:
        try:
            from src.services.bi import forecasting as F
            d["forecast_liquidez"] = F.forecast_liquidez(id_empresa)
        except Exception:
            pass
    _audit("BI_DASHBOARD_ABIERTO", f"periodo={periodo}")
    return d


def comparar_empresas(empresas, codigo, *, periodo="mes", fecha=None) -> list:
    """Valor de un KPI en varias empresas (uso SUPERADMIN). Cada cálculo usa su propio tenant."""
    out = []
    for emp in empresas:
        vals = _K.calcular_kpi(_dominio_de(codigo), periodo=periodo, fecha=fecha,
                               id_empresa=emp, persistir=False)
        out.append({"id_empresa": emp, "codigo": codigo, "valor": vals.get(codigo, 0.0)})
    return out


def _dominio_de(codigo):
    return codigo.split(".", 1)[0]


def exportar(datos, formato="json") -> str:
    """Exporta un dashboard/comparativa a JSON o CSV (plano de KPIs)."""
    formato = (formato or "json").lower()
    if formato == "json":
        _audit("BI_EXPORTACION", "json")
        return json.dumps(datos, ensure_ascii=False, default=str, indent=2)
    # CSV plano: dominio;codigo;nombre;valor (si es panel) o id_empresa;codigo;valor (comparativa).
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    if isinstance(datos, dict) and "secciones" in datos:
        w.writerow(["dominio", "codigo", "nombre", "valor"])
        for dom, items in datos["secciones"].items():
            for it in items:
                w.writerow([dom, it["codigo"], it.get("nombre"), it["valor"]])
    elif isinstance(datos, list):
        w.writerow(["id_empresa", "codigo", "valor"])
        for r in datos:
            w.writerow([r.get("id_empresa"), r.get("codigo"), r.get("valor")])
    _audit("BI_EXPORTACION", "csv")
    return buf.getvalue()


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bi", accion, "bi_kpi_valores", detalle)
    except Exception:
        pass

def _gate(modulo, id_empresa):
    """Enforcement SaaS (legacy-safe): bloquea si el plan no incluye el módulo."""
    try:
        from src.services.saas import enforcement as _enf
        _enf.exigir_modulo(modulo, id_empresa)
    except ImportError:
        pass
