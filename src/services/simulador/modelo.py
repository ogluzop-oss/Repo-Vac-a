"""
Modelo del Simulador Empresarial (Paquete Enterprise 9). Estados de escenario, niveles de
confianza y contrato de metricas normalizadas sobre las que opera el motor what-if. Nada de esto
toca datos reales: son estructuras virtuales en memoria/escenario.
"""

# Estados del escenario
BORRADOR = "BORRADOR"
SIMULADO = "SIMULADO"
ARCHIVADO = "ARCHIVADO"

# Niveles de confianza de una simulacion (explicabilidad, SUBFASE 9.15)
CONF_ALTA = "ALTA"
CONF_MEDIA = "MEDIA"
CONF_BAJA = "BAJA"

# Metricas normalizadas del "cuadro de mando" simulado (periodo base: ~30 dias).
METRICAS = ("ingresos", "unidades", "coste_ventas", "coste_personal", "gastos", "iva",
            "beneficio", "margen_pct", "liquidez", "plantilla", "stock_roturas")

# Dominios de variables what-if
DOMINIOS = ("comercial", "logistica", "rrhh", "financiera", "fiscal", "estructura")


def metricas_vacias() -> dict:
    return {m: 0.0 for m in METRICAS}


def confianza_por_variables(n_variables, dominios) -> str:
    """Menos variables y dominios acotados → mas confianza; cambios cruzados amplios → menos."""
    if n_variables <= 1:
        return CONF_ALTA
    if n_variables <= 3 and len(set(dominios)) <= 2:
        return CONF_MEDIA
    return CONF_BAJA
