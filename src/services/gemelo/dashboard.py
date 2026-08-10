"""
Backend del panel de estado vivo del Gemelo Digital (Paquete Enterprise 8, SUBFASE 8.14).

Prepara los indicadores para un panel directivo alimentado integramente por el gemelo: empresas,
tiendas, almacenes, usuarios, stock, ventas, pedidos, facturas, contratos, sincronizacion,
automatizaciones y riesgos. Solo lectura y agregado; no recorre todas las tablas (SUBFASE 8.16).
"""

from src.services.gemelo import modelo as M


def _svc():
    from src.services.gemelo import motor
    return motor.servicio()


def panel(id_empresa=None) -> dict:
    svc = _svc()
    estados = svc.estados(id_empresa)          # dict dominio -> estado
    glob = estados.get("empresa", {})
    ind = glob.get("indicadores", {})
    inv = estados.get("inventario", {}).get("indicadores", {})
    com = estados.get("comercial", {}).get("indicadores", {})
    fin = estados.get("financiero", {}).get("indicadores", {})
    rrh = estados.get("rrhh", {}).get("indicadores", {})
    log = estados.get("logistico", {}).get("indicadores", {})

    riesgo_global = M.peor_riesgo(*[e.get("riesgo", M.RIESGO_BAJO) for e in estados.values()])
    alertas = []
    for e in estados.values():
        alertas += [{"dominio": e.get("dominio"), "texto": a} for a in e.get("alertas", [])]

    return {
        "riesgo_global": riesgo_global,
        "indicadores": {
            "empresas": ind.get("empresas", 0),
            "tiendas": ind.get("tiendas", 0),
            "almacenes": ind.get("almacenes", 0),
            "usuarios": ind.get("usuarios", 0),
            "stock_roturas": inv.get("roturas_previstas", 0),
            "stock_sobrestock": inv.get("sobrestock_previsto", 0),
            "ventas_30d": com.get("ventas_30d", 0),
            "pedidos_pendientes": ind.get("pedidos_pendientes", log.get("pedidos_pendientes", 0)),
            "facturas_pendientes": ind.get("facturas_pendientes", 0),
            "impagos": com.get("impagos", 0),
            "liquidez": fin.get("liquidez_disponible", 0),
            "contratos_por_vencer": rrh.get("contratos_por_vencer", 0),
            "tiendas_offline": ind.get("tiendas_offline", 0),
            "automatizaciones_pendientes": ind.get("automatizaciones_pendientes", 0),
            "incidencias_abiertas": ind.get("incidencias_abiertas", 0),
        },
        "riesgos_por_dominio": {d: e.get("riesgo") for d, e in estados.items()},
        "alertas": alertas,
        "resumen": glob.get("resumen", ""),
    }
