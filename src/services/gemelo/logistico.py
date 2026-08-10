"""
Gemelo Digital Logistico (Paquete Enterprise 8, SUBFASE 8.7). Representa: proveedores, compras,
recepciones, envios, repartos y estado logistico. Reutiliza la Sincronizacion Enterprise (Centro
de Actividad) para el estado de terminales/reparto y consultas de solo lectura; no duplica el
modulo de compras ni el kardex.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)

    proveedores = F.contar("SELECT COUNT(*) FROM proveedores WHERE id_empresa=%s", (emp,))
    pedidos_pend = F.contar("SELECT COUNT(*) FROM compras_pedidos WHERE id_empresa=%s "
                            "AND estado IN ('BORRADOR','ENVIADO','PENDIENTE','PARCIAL')", (emp,))
    # Recepciones pendientes: pedidos enviados aun sin recepcionar por completo.
    recep_pend = F.contar("SELECT COUNT(*) FROM compras_pedidos WHERE id_empresa=%s "
                          "AND estado IN ('ENVIADO','PARCIAL')", (emp,))
    envios_pend = F.contar("SELECT COUNT(*) FROM factura_envios WHERE id_empresa=%s "
                           "AND estado IN ('pendiente','preparando','en_reparto')", (emp,))

    infra = F.infraestructura(emp)
    glob = infra.get("global", {}) or {}
    terminales_off = len([t for t in (infra.get("terminales", []) or [])
                          if str(t.get("estado")).upper() == "OFFLINE"])

    ind = {
        "proveedores": proveedores,
        "pedidos_pendientes": pedidos_pend,
        "recepciones_pendientes": recep_pend,
        "envios_pendientes": envios_pend,
        "terminales_offline": terminales_off,
        "sincronizacion": glob,
    }
    riesgo = M.RIESGO_BAJO
    alertas = []
    if terminales_off:
        alertas.append(f"{terminales_off} terminal(es) logisticos offline")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_ALTO)
    if recep_pend:
        alertas.append(f"{recep_pend} recepcion(es) pendientes")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)

    resumen = (f"{proveedores} proveedores; {pedidos_pend} pedidos, {recep_pend} recepciones y "
               f"{envios_pend} envios pendientes.")
    return M.estado_dominio("logistico", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"infraestructura": glob})
