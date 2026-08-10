"""
CRM predictivo (Paquete Enterprise 3, SUBFASE 3.7). Clasifica clientes (activos/crecimiento/
descenso/inactivos) desde su actividad de ventas y propone actuaciones (contactar/seguimiento/
promocion). Solo recomienda. Best-effort (vacio si no hay historico de ventas por cliente).
"""

from datetime import datetime

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C


def predecir(id_empresa=None) -> dict:
    if not C.activo("crm", id_empresa):
        return {"dominio": "crm", "activo": False, "clientes": {}, "recomendaciones": []}
    act = A.clientes_por_actividad(id_empresa, dias=90)
    inactivos, estrategicos, crecimiento = [], [], []
    hoy = datetime.now()
    for c in act:
        importe = float(c.get("importe") or 0)
        ultima = c.get("ultima")
        dias_ultima = None
        try:
            if ultima:
                dias_ultima = (hoy - (ultima if isinstance(ultima, datetime)
                                      else datetime.fromisoformat(str(ultima)[:19]))).days
        except Exception:
            dias_ultima = None
        if dias_ultima is not None and dias_ultima > 45:
            inactivos.append({**c, "dias_sin_comprar": dias_ultima})
        if importe > 0:
            estrategicos.append(c)
    estrategicos = sorted(estrategicos, key=lambda x: float(x.get("importe") or 0), reverse=True)[:10]

    recomendaciones = []
    for c in inactivos[:15]:
        recomendaciones.append({"accion": "contactar / seguimiento", "entidad": "cliente",
                                "entidad_id": c.get("cliente_id"),
                                "motivo": f"Sin comprar hace {c.get('dias_sin_comprar')} dias",
                                "prioridad": "MEDIA", "workflow": "documento"})
    for c in estrategicos[:5]:
        recomendaciones.append({"accion": "ofrecer promocion / visita", "entidad": "cliente",
                                "entidad_id": c.get("cliente_id"),
                                "motivo": f"Cliente estrategico ({float(c.get('importe') or 0):.0f})",
                                "prioridad": "BAJA", "workflow": ""})
    alertas = []
    if inactivos:
        alertas.append({"tipo": "crm", "severidad": "media",
                        "mensaje": f"{len(inactivos)} clientes inactivos (posible perdida).",
                        "datos": {"n": len(inactivos)}})
    return {"dominio": "crm", "activo": True,
            "clientes": {"inactivos": len(inactivos), "estrategicos": len(estrategicos)},
            "recomendaciones": recomendaciones, "alertas": alertas}
