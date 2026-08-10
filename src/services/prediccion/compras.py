"""
Prediccion de compras / aprovisionamiento (Paquete Enterprise 3, SUBFASE 3.4). Recomienda
comprar ahora / esperar / reducir, en funcion de stock, rotacion y demanda estimada. Nunca crea
pedidos: delega en Workflow/BPM.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C


def predecir(id_empresa=None) -> dict:
    if not C.activo("compras", id_empresa):
        return {"dominio": "compras", "activo": False, "recomendaciones": [], "alertas": []}
    bajo = A.articulos_bajo_umbral(id_empresa)
    exc = A.articulos_exceso(id_empresa)
    rot = {r.get("codigo"): int(r.get("uds") or 0) for r in A.rotacion_articulos(id_empresa)}
    recomendaciones = []
    for a in bajo[:25]:
        prisa = "urgente" if rot.get(a["codigo"], 0) > 0 else "normal"
        recomendaciones.append({
            "accion": "comprar ahora" if prisa == "urgente" else "comprar",
            "entidad": "articulo", "entidad_id": a["codigo"],
            "motivo": f"Bajo umbral (faltan {a.get('faltan')}). Rotacion {rot.get(a['codigo'], 0)} uds/30d.",
            "prioridad": "ALTA" if prisa == "urgente" else "MEDIA", "workflow": "compras_pedido"})
    for a in exc[:10]:
        recomendaciones.append({"accion": "reducir compra", "entidad": "articulo",
                                "entidad_id": a["codigo"], "motivo": f"Exceso +{a.get('exceso')}",
                                "prioridad": "BAJA", "workflow": ""})
    alertas = []
    if bajo:
        alertas.append({"tipo": "compras", "severidad": "media",
                        "mensaje": f"{len(bajo)} articulos requieren aprovisionamiento.",
                        "datos": {"n": len(bajo)}})
    return {"dominio": "compras", "activo": True, "recomendaciones": recomendaciones,
            "alertas": alertas}
