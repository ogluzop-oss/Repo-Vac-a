"""
Prediccion de stock (Paquete Enterprise 3, SUBFASE 3.2). Anticipa roturas, sobrestock,
reposiciones necesarias, productos sin movimiento y de alta rotacion. Solo recomienda; nunca
modifica inventario.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C
from src.services.prediccion import estadisticas as E
from src.services.prediccion import forecasting as F
from src.services.prediccion import tendencias as T

_ETIQUETA = {"ml": "Machine Learning (Prophet)", "estadistica": "modelo estadístico",
             "heuristica": "estimación heurística"}


def predecir(id_empresa=None) -> dict:
    if not C.activo("stock", id_empresa):
        return {"dominio": "stock", "activo": False, "predicciones": [], "alertas": []}
    bajo = A.articulos_bajo_umbral(id_empresa)
    exc = A.articulos_exceso(id_empresa)
    parados = A.sin_movimiento(id_empresa)
    rotacion = A.rotacion_articulos(id_empresa)
    rows = A.ventas_por_dia(id_empresa, dias=90)
    serie = [float(v.get("total") or 0) for v in rows]
    fechas = [str(v.get("d")) for v in rows]
    conf = E.confianza(serie)
    # Demanda con el motor predictivo REAL (Machine Learning si hay datos; si no estadística/heurística).
    fc = F.forecast(serie, fechas=fechas, horizonte=7, id_empresa=id_empresa, entidad="ventas",
                    emitir=False, persistir=False)
    pred = fc.get("prediccion") or []
    demanda = round(sum(pred[:7]), 2) if pred else 0.0

    predicciones = [
        {"metrica": "rotura_stock", "horizonte": "7 dias", "valor": len(bajo), "confianza": conf,
         "detalle": f"{len(bajo)} articulos en riesgo de rotura"},
        {"metrica": "sobrestock", "horizonte": "actual", "valor": len(exc), "confianza": 0.6,
         "detalle": f"{len(exc)} articulos con exceso"},
        {"metrica": "sin_movimiento", "horizonte": "60 dias", "valor": len(parados), "confianza": 0.7,
         "detalle": f"{len(parados)} productos sin ventas"},
        {"metrica": "demanda", "horizonte": "proxima semana", "valor": demanda,
         "confianza": conf, "detalle": f"Demanda estimada (uds) — {_ETIQUETA.get(fc.get('tipo'), fc.get('modelo'))}"},
    ]
    alertas = []
    if bajo:
        alertas.append({"tipo": "stock", "severidad": "alta" if len(bajo) > 10 else "media",
                        "mensaje": f"No habra stock suficiente en {len(bajo)} articulos.",
                        "datos": {"n": len(bajo)}})
    if exc:
        alertas.append({"tipo": "stock", "severidad": "media",
                        "mensaje": f"Habra exceso de inventario en {len(exc)} articulos.",
                        "datos": {"n": len(exc)}})
    return {"dominio": "stock", "activo": True, "predicciones": predicciones, "alertas": alertas,
            "alta_rotacion": rotacion[:10], "sin_movimiento": parados[:10],
            "tendencia_demanda": T.analizar(serie),
            "modelo": fc.get("modelo"), "tipo": fc.get("tipo"), "es_ml": fc.get("es_ml", False)}
