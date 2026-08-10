"""
Gemelo Digital Comercial (Paquete Enterprise 8, SUBFASE 8.4). Representa: clientes, ventas,
pedidos, facturacion, impagos, rentabilidad y estado comercial. Reutiliza PredictionService
(clientes/ventas), BI (margen/KPIs) y consultas de solo lectura; no duplica el CRM ni ventas.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)

    ventas_30 = F.filas("SELECT COALESCE(SUM(total),0) t, COUNT(*) n FROM ventas WHERE id_empresa=%s "
                        "AND fecha >= (NOW() - INTERVAL 30 DAY)", (emp,))
    total_30 = float((ventas_30[0].get("t") if ventas_30 else 0) or 0)
    tickets_30 = int((ventas_30[0].get("n") if ventas_30 else 0) or 0)

    clientes = F.contar("SELECT COUNT(*) FROM clientes WHERE id_empresa=%s", (emp,))
    facturas_pend = F.contar("SELECT COUNT(*) FROM facturas_cliente WHERE id_empresa=%s "
                             "AND estado IN ('pendiente','emitida')", (emp,))
    impagos = F.contar("SELECT COUNT(*) FROM facturas_cliente WHERE id_empresa=%s "
                       "AND estado='impagada'", (emp,))
    pedidos_pend = F.contar("SELECT COUNT(*) FROM ventas_pedidos_cliente WHERE id_empresa=%s "
                            "AND estado IN ('borrador','confirmado','pendiente','parcial')", (emp,))

    inactivos = 0
    detalle = {}
    try:
        cl = F.prediccion().clientes(emp)
        detalle = cl
        inactivos = int((cl.get("clientes") or {}).get("inactivos", 0) or 0)
    except Exception:
        pass

    ind = {
        "clientes": clientes,
        "ventas_30d": round(total_30, 2),
        "tickets_30d": tickets_30,
        "ticket_medio": round(total_30 / tickets_30, 2) if tickets_30 else 0,
        "facturas_pendientes": facturas_pend,
        "impagos": impagos,
        "pedidos_pendientes": pedidos_pend,
        "clientes_inactivos": inactivos,
    }
    riesgo = M.RIESGO_BAJO
    alertas = []
    if impagos:
        alertas.append(f"{impagos} factura(s) impagada(s)")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_ALTO)
    if inactivos:
        alertas.append(f"{inactivos} cliente(s) inactivos")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)

    resumen = (f"{clientes} clientes; ventas 30d {round(total_30, 2)} ({tickets_30} tickets); "
               f"{facturas_pend} facturas pendientes, {impagos} impagos.")
    return M.estado_dominio("comercial", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"prediccion_clientes": detalle})
