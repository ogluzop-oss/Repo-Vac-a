"""
RRHH predictivo (Paquete Enterprise 3, SUBFASE 3.6). Anticipa contratos por vencer y riesgo de
falta de cobertura a partir de la informacion existente. Solo lectura.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C


def predecir(id_empresa=None) -> dict:
    if not C.activo("rrhh", id_empresa):
        return {"dominio": "rrhh", "activo": False, "predicciones": [], "alertas": []}
    cv = A.contratos_por_vencer(id_empresa)
    predicciones = [
        {"metrica": "contratos_por_vencer", "horizonte": "30 dias", "valor": len(cv),
         "confianza": 0.9, "detalle": f"{len(cv)} contratos vencen en 30 dias"},
    ]
    alertas = []
    if cv:
        alertas.append({"tipo": "rrhh", "severidad": "media" if len(cv) < 5 else "alta",
                        "mensaje": f"{len(cv)} contratos proximos a vencer: riesgo de falta de cobertura.",
                        "datos": {"n": len(cv)}})
    return {"dominio": "rrhh", "activo": True, "predicciones": predicciones, "alertas": alertas}
