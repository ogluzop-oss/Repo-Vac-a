"""
Indicadores y oportunidades para el dashboard predictivo (Paquete Enterprise 3, SUBFASE
3.9/3.11). Complementa BI (no lo sustituye): destaca oportunidades y titulares predictivos.
"""

from src.services.prediccion import adaptadores as A


def oportunidades(id_empresa=None) -> list:
    """Oportunidades detectadas (productos estrella, clientes estrategicos)."""
    op = []
    for r in A.rotacion_articulos(id_empresa)[:5]:
        op.append({"tipo": "producto_estrella", "entidad": r.get("codigo"),
                   "detalle": f"Alta rotacion ({int(r.get('uds') or 0)} uds/30d)"})
    return op


def titulares(id_empresa=None) -> list:
    """Titulares predictivos rapidos (numeros clave)."""
    bajo = A.articulos_bajo_umbral(id_empresa)
    exc = A.articulos_exceso(id_empresa)
    fp = A.facturas_pendientes(id_empresa)
    return [
        {"indicador": "Riesgo de rotura", "valor": len(bajo)},
        {"indicador": "Exceso de stock", "valor": len(exc)},
        {"indicador": "Facturas por cobrar", "valor": len(fp)},
    ]
