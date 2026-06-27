"""
FASE D — Catalogo unificado de KPIs corporativos. Cada KPI mapea a (dominio, metrica) del DW.
Calcula desde dw_hechos (ya poblado por el ETL) + rentabilidades derivadas. Multiempresa.
"""

import logging
from src.services.bi_corp import olap
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.kpis")

# codigo corporativo -> (dominio, metrica, etiqueta, unidad)
CATALOGO = {
    "facturacion": ("ventas", "facturacion", "Facturacion", "€"),
    "ticket_medio": ("ventas", "ticket_medio", "Ticket medio", "€"),
    "margen": ("ventas", "margen_bruto", "Margen bruto", "€"),
    "gasto_compras": ("compras", "gasto_total", "Gasto en compras", "€"),
    "valor_stock": ("stock", "valor", "Valor de inventario", "€"),
    "roturas_stock": ("stock", "roturas", "Roturas de stock", "ud"),
    "coste_laboral": ("rrhh", "coste_laboral", "Coste laboral", "€"),
    "plantilla": ("rrhh", "plantilla_activa", "Plantilla activa", "ud"),
    "tesoreria_disponible": ("tesoreria", "disponible", "Tesoreria disponible", "€"),
    "cash_flow": ("tesoreria", "previsto", "Cash flow previsto", "€"),
    "ebitda": ("finanzas", "ebitda", "EBITDA", "€"),
    "endeudamiento": ("finanzas", "endeudamiento", "Endeudamiento", "ratio"),
    "roe": ("finanzas", "roe", "ROE", "%"),
    "cash_conversion_cycle": ("finanzas", "cash_conversion_cycle", "Ciclo conversion caja", "dias"),
    "conversion_crm": ("crm", "conversion_pct", "Conversion CRM", "%"),
    "forecast_comercial": ("crm", "forecast", "Forecast comercial", "€"),
    "mttr": ("gmao", "mttr_horas", "MTTR", "h"),
    "mtbf": ("gmao", "mtbf_horas", "MTBF", "h"),
    "disponibilidad_activos": ("gmao", "disponibilidad_pct", "Disponibilidad activos", "%"),
    "tiempo_resolucion_sat": ("sat", "tiempo_resolucion_horas", "Tiempo resolucion SAT", "h"),
    "cumplimiento_sla": ("sat", "cumplimiento_sla_pct", "Cumplimiento SLA", "%"),
    "tasa_rechazo": ("calidad", "tasa_rechazo_pct", "Tasa de rechazo", "%"),
    "eficiencia_produccion": ("produccion", "eficiencia_pct", "Eficiencia produccion", "%"),
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def valor_kpi(codigo, *, periodo=None, id_empresa=None) -> dict:
    if codigo not in CATALOGO:
        return {"ok": False, "error": "kpi desconocido"}
    dom, met, etiqueta, unidad = CATALOGO[codigo]
    filtros = {"metrica": met, "dominio": dom}
    if periodo:
        filtros["periodo"] = periodo
    filas = olap.cubo(dimensiones=("metrica",), filtros=filtros, agregacion="sum", id_empresa=_emp(id_empresa))
    valor = float(filas[0]["valor"]) if filas else 0.0
    return {"ok": True, "codigo": codigo, "etiqueta": etiqueta, "valor": round(valor, 2), "unidad": unidad}


def cuadro(*, periodo=None, id_empresa=None) -> list:
    """Devuelve el cuadro completo de KPIs corporativos."""
    return [valor_kpi(c, periodo=periodo, id_empresa=id_empresa) for c in CATALOGO]


def rentabilidad_por(dimension, *, id_empresa=None) -> list:
    """Rentabilidad por tienda/cliente/producto = facturacion - coste, agregada del DW.
    dimension in ('id_tienda',). Para cliente/producto usa dims; aproximacion sobre ventas/margen."""
    eid = _emp(id_empresa)
    if dimension == "id_tienda":
        fact = {f["id_tienda"]: float(f["valor"]) for f in
                olap.cubo(dimensiones=("id_tienda",), filtros={"metrica": "facturacion"}, id_empresa=eid)}
        margen = {f["id_tienda"]: float(f["valor"]) for f in
                  olap.cubo(dimensiones=("id_tienda",), filtros={"metrica": "margen_bruto"}, id_empresa=eid)}
        return sorted([{"id_tienda": t, "facturacion": round(v, 2), "margen": round(margen.get(t, 0), 2)}
                       for t, v in fact.items()], key=lambda x: x["margen"], reverse=True)
    return []
