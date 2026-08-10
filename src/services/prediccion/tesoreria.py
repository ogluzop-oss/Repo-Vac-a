"""
Tesoreria predictiva (Paquete Enterprise 3, SUBFASE 3.5). Anticipa riesgo de liquidez, impagos
y clientes morosos a partir de facturas/cobros existentes. Solo lectura.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C


def predecir(id_empresa=None) -> dict:
    if not C.activo("tesoreria", id_empresa):
        return {"dominio": "tesoreria", "activo": False, "predicciones": [], "alertas": []}
    fp = A.facturas_pendientes(id_empresa)
    importe = round(sum(float(f.get("total") or 0) for f in fp), 2)
    predicciones = [
        {"metrica": "cobros_pendientes", "horizonte": "actual", "valor": importe, "confianza": 0.75,
         "detalle": f"{len(fp)} facturas por cobrar"},
        {"metrica": "riesgo_liquidez", "horizonte": "30 dias",
         "valor": "alto" if len(fp) >= 10 else ("medio" if len(fp) >= 3 else "bajo"),
         "confianza": 0.6, "detalle": "Segun cartera pendiente de cobro"},
    ]
    alertas = []
    if len(fp) >= 5:
        alertas.append({"tipo": "tesoreria", "severidad": "alta",
                        "mensaje": f"Existe riesgo elevado de impago: {len(fp)} facturas pendientes ({importe:.2f}).",
                        "datos": {"n": len(fp), "importe": importe}})
    return {"dominio": "tesoreria", "activo": True, "predicciones": predicciones, "alertas": alertas}
