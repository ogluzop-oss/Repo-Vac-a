"""
FASE C — Dashboard corporativo global. Agrega todas las secciones (ventas/compras/stock/finanzas/
tesoreria/rrhh/crm/sat/gmao/calidad/produccion/fiscalidad) + KPIs estrategicos, forecast, alertas e
IA ejecutiva sobre el DW. Multiempresa/tienda/almacen. Solo lectura (no toca transaccional).
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.dashboard")

SECCIONES = ("ventas", "compras", "stock", "finanzas", "tesoreria", "rrhh", "crm", "sat",
             "gmao", "calidad", "produccion", "fiscalidad")
# Mapa seccion -> dominio DW (fiscalidad reutiliza aeat).
_DOMINIO = {"fiscalidad": "aeat"}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def panel(*, periodo=None, id_empresa=None, con_forecast=False, con_ia=False,
          id_tienda=None, id_almacen=None) -> dict:
    """Cuadro de mando corporativo. Devuelve secciones (metricas del DW) + KPIs estrategicos."""
    eid = _emp(id_empresa)
    from src.services.bi_corp import kpis_corp, olap

    secciones = {}
    for sec in SECCIONES:
        dom = _DOMINIO.get(sec, sec)
        filtros = {"dominio": dom}
        if periodo:
            filtros["periodo"] = periodo
        if id_tienda is not None:
            filtros["id_tienda"] = id_tienda
        if id_almacen is not None:
            filtros["id_almacen"] = id_almacen
        filas = olap.cubo(dimensiones=("metrica",), filtros=filtros, agregacion="sum", id_empresa=eid)
        secciones[sec] = {f["metrica"]: round(float(f["valor"]), 2) for f in filas}

    out = {
        "periodo": periodo, "id_empresa": eid,
        "secciones": secciones,
        "kpis_estrategicos": [k for k in kpis_corp.cuadro(periodo=periodo, id_empresa=eid) if k.get("ok")],
    }
    if con_forecast:
        from src.services.bi_corp import forecast_corp
        out["forecast"] = forecast_corp.forecast_global(id_empresa=eid)
    if con_ia:
        from src.services.bi_corp import alertas, ia_ejecutiva
        out["alertas"] = alertas.detectar(id_empresa=eid)
        out["ia_ejecutiva"] = ia_ejecutiva.informe(id_empresa=eid)
    return out


def panel_multiempresa(metricas, *, empresas=None, periodo=None) -> dict:
    """Cuadro de mando consolidado de varias empresas (FASE E)."""
    from src.services.bi_corp import consolidacion
    return consolidacion.consolidar(metricas, empresas=empresas, periodo=periodo)


def exportar_panel(panel_data, formato="json", *, nombre="dashboard_corp") -> dict:
    """Aplana el panel a filas y lo exporta (FASE I)."""
    from src.services.bi_corp import export
    filas = []
    for sec, mets in (panel_data.get("secciones") or {}).items():
        for met, val in mets.items():
            filas.append({"seccion": sec, "metrica": met, "valor": val})
    for k in panel_data.get("kpis_estrategicos", []):
        filas.append({"seccion": "kpi", "metrica": k.get("codigo"), "valor": k.get("valor"),
                      "unidad": k.get("unidad")})
    return export.exportar(filas, formato, nombre=nombre)
