"""
Estado BASE del simulador (Paquete Enterprise 9, SUBFASE 9.17). Extrae del Gemelo Digital el cuadro
de metricas de partida sobre el que se simula. NO recorre el ERP: reutiliza integramente el
DigitalTwinService (que a su vez reutiliza PredictionService/BI/Tesoreria). Solo lectura.

Algunas magnitudes no existen como dato directo (coste de ventas, coste de personal, IVA); se
derivan con HIPOTESIS transparentes (margen/salario/tipo IVA por defecto), declaradas luego en la
explicabilidad (SUBFASE 9.15). El simulador nunca inventa sin decirlo.
"""

import logging

logger = logging.getLogger("simulador.base")

# Hipotesis por defecto (configurables, declaradas en la explicabilidad).
MARGEN_BRUTO_DEF = 0.30       # 30% de margen bruto → coste_ventas = ingresos * (1 - margen)
SALARIO_MEDIO_MES = 1800.0    # coste medio de personal por empleado y mes (con proxy)
IVA_TIPO_DEF = 0.21           # tipo IVA por defecto para estimar la cuota sobre ingresos
GASTOS_PCT_DEF = 0.10         # otros gastos operativos ~10% de ingresos


def _emp(id_empresa=None):
    # IOC v3 (Bloque VI): adopción — resolución vía IOC (sin depender del shim deprecado fuentes.emp).
    try:
        from src.services.identidad import _base as _ioc
        return _ioc.emp(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _twin(id_empresa):
    from src.services import gemelo
    return gemelo.servicio().estado_empresa(id_empresa)


def metricas_base(id_empresa=None) -> dict:
    """Cuadro de metricas de partida (periodo ~30 dias) derivado del Gemelo Digital."""
    emp = _emp(id_empresa)
    dominios = {}
    try:
        g = _twin(emp)
        dominios = g.get("dominios", {})
    except Exception as e:
        logger.debug("metricas_base twin: %s", e)

    com = dominios.get("comercial", {}).get("indicadores", {})
    fin = dominios.get("financiero", {}).get("indicadores", {})
    rrh = dominios.get("rrhh", {}).get("indicadores", {})
    inv = dominios.get("inventario", {}).get("indicadores", {})

    ingresos = float(com.get("ventas_30d", 0) or 0)
    unidades = float(com.get("tickets_30d", 0) or 0)
    plantilla = int(rrh.get("empleados", 0) or 0)
    liquidez = float(fin.get("liquidez_disponible", 0) or 0)
    roturas = int(inv.get("roturas_previstas", 0) or 0)

    coste_ventas = round(ingresos * (1 - MARGEN_BRUTO_DEF), 2)
    coste_personal = round(plantilla * SALARIO_MEDIO_MES, 2)
    gastos = round(ingresos * GASTOS_PCT_DEF, 2)
    iva = round(ingresos * IVA_TIPO_DEF, 2)
    beneficio = round(ingresos - coste_ventas - coste_personal - gastos, 2)
    margen = round((beneficio / ingresos * 100) if ingresos else 0.0, 2)

    return {
        "ingresos": round(ingresos, 2),
        "unidades": round(unidades, 2),
        "coste_ventas": coste_ventas,
        "coste_personal": coste_personal,
        "gastos": gastos,
        "iva": iva,
        "beneficio": beneficio,
        "margen_pct": margen,
        "liquidez": round(liquidez, 2),
        "plantilla": plantilla,
        "stock_roturas": roturas,
    }


def hipotesis() -> dict:
    """Hipotesis usadas al derivar el estado base (para la explicabilidad)."""
    return {
        "margen_bruto": MARGEN_BRUTO_DEF,
        "salario_medio_mes": SALARIO_MEDIO_MES,
        "tipo_iva": IVA_TIPO_DEF,
        "gastos_pct": GASTOS_PCT_DEF,
        "periodo": "30 dias",
        "fuente": "DigitalTwinService (Gemelo Digital)",
    }
