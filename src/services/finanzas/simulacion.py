"""
FASE E — Motor de simulacion financiera What-If. NO modifica datos reales: parte de la foto
actual (ratios/tesoreria/PyG) y aplica variaciones a variables (ventas/costes/salarios/compras/
financiacion/impagos/inflacion/tipos de interes) calculando el impacto sobre tesoreria/beneficio/
EBITDA/liquidez/endeudamiento. Escenarios en memoria (temporales). Auditado.
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.simulacion")

# Variables soportadas y a que magnitud afectan (factor multiplicativo sobre la base, en %).
VARIABLES = ("ventas", "costes", "salarios", "compras", "financiacion", "impagos", "inflacion", "tipos_interes")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _foto_base(eid) -> dict:
    """Foto financiera actual (no se modifica). Ingresos/gastos/beneficio/tesoreria/deuda."""
    base = {"ingresos": 0.0, "gastos": 0.0, "salarios": 0.0, "compras": 0.0, "disponible": 0.0,
            "deuda": 0.0, "intereses": 0.0}
    try:
        from src.services.contabilidad import informes
        pyg = informes.perdidas_ganancias(id_empresa=eid)
        base["ingresos"] = float(pyg.get("ingresos", 0) or 0)
        base["gastos"] = float(pyg.get("gastos", 0) or 0)
    except Exception:
        pass
    try:
        from src.services.tesoreria import posicion
        base["disponible"] = float(posicion.posicion(id_empresa=eid).get("disponible", 0) or 0)
    except Exception:
        pass
    try:
        from src.services.finanzas import financiacion
        base["deuda"] = float(financiacion.deuda_viva(id_empresa=eid)["total"])
    except Exception:
        pass
    return base


def simular(variaciones: dict, *, id_empresa=None) -> dict:
    """variaciones: {variable: pct} (p.ej. {'ventas': +10, 'costes': -5, 'tipos_interes': +1}).
    Devuelve foto base, foto simulada e impacto sobre KPIs clave. No persiste nada."""
    eid = _emp(id_empresa)
    base = _foto_base(eid)
    v = {k: float(variaciones.get(k, 0)) for k in VARIABLES}

    ingresos = base["ingresos"] * (1 + v["ventas"] / 100)
    # Impagos reducen ingresos efectivos.
    ingresos_efectivos = ingresos * (1 - max(0, v["impagos"]) / 100)
    # Costes: variacion combinada de costes generales + inflacion + (salarios y compras como
    # componentes del gasto). Modelo lineal transparente sobre el gasto base.
    pct_gasto = v["costes"] + v["inflacion"] + v["salarios"] + v["compras"]
    gastos = base["gastos"] * (1 + pct_gasto / 100)
    # Deuda y coste financiero por variacion de tipos.
    deuda = base["deuda"] * (1 + v["financiacion"] / 100)
    intereses_extra = deuda * (v["tipos_interes"] / 100)

    beneficio_base = base["ingresos"] - base["gastos"]
    beneficio_sim = round(ingresos_efectivos - gastos - intereses_extra, 2)
    ebitda_sim = round(beneficio_sim + intereses_extra, 2)
    tesoreria_sim = round(base["disponible"] + (beneficio_sim - beneficio_base), 2)
    endeudamiento_sim = round(deuda, 2)

    impacto = {
        "beneficio": {"base": round(beneficio_base, 2), "simulado": beneficio_sim,
                      "delta": round(beneficio_sim - beneficio_base, 2)},
        "ebitda": {"simulado": ebitda_sim},
        "tesoreria": {"base": round(base["disponible"], 2), "simulado": tesoreria_sim,
                      "delta": round(tesoreria_sim - base["disponible"], 2)},
        "liquidez": {"riesgo": tesoreria_sim < 0},
        "endeudamiento": {"base": round(base["deuda"], 2), "simulado": endeudamiento_sim},
    }
    _audit(eid, variaciones)
    return {"variaciones": v, "base": base, "impacto": impacto}


def comparar_escenarios(escenarios: dict, *, id_empresa=None) -> dict:
    """escenarios: {nombre: variaciones}. Devuelve el impacto de cada uno (todo en memoria)."""
    eid = _emp(id_empresa)
    return {nombre: simular(var, id_empresa=eid)["impacto"] for nombre, var in (escenarios or {}).items()}


def _audit(eid, variaciones):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("finanzas", "FIN_SIMULACION", "simulacion", str(variaciones)[:200])
    except Exception:
        pass
