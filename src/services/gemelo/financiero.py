"""
Gemelo Digital Financiero (Paquete Enterprise 8, SUBFASE 8.6). Representa: tesoreria, cobros,
pagos, riesgos, liquidez, facturacion y cuentas pendientes. Reutiliza el servicio de Tesoreria
(posicion de liquidez), PredictionService (riesgos financieros) y consultas de solo lectura; no
duplica la tesoreria ni la contabilidad.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def _num(d, *claves, defecto=0.0):
    for k in claves:
        if isinstance(d, dict) and d.get(k) is not None:
            try:
                return float(d.get(k))
            except (TypeError, ValueError):
                continue
    return defecto


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)
    pos = F.posicion_tesoreria(emp)
    disponible = _num(pos, "disponible", "saldo", "saldo_total", "liquidez")
    cobros_pend = _num(pos, "cobros_pendientes", "por_cobrar", "ar_pendiente")
    pagos_pend = _num(pos, "pagos_pendientes", "por_pagar", "ap_pendiente")

    if not cobros_pend:
        cobros_pend = F.contar("SELECT COUNT(*) FROM vencimientos WHERE id_empresa=%s "
                               "AND tipo='COBRO' AND estado IN ('PENDIENTE','VENCIDO')", (emp,))
    if not pagos_pend:
        pagos_pend = F.contar("SELECT COUNT(*) FROM vencimientos WHERE id_empresa=%s "
                              "AND tipo='PAGO' AND estado IN ('PENDIENTE','VENCIDO')", (emp,))

    impagos = F.contar("SELECT COUNT(*) FROM facturas_cliente WHERE id_empresa=%s "
                       "AND estado='impagada'", (emp,))

    ind = {
        "liquidez_disponible": round(disponible, 2),
        "cobros_pendientes": cobros_pend,
        "pagos_pendientes": pagos_pend,
        "impagos": impagos,
    }
    riesgo = M.RIESGO_BAJO
    alertas = []
    if disponible < 0:
        alertas.append("Liquidez negativa")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_ALTO)
    if impagos:
        alertas.append(f"{impagos} impago(s)")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)

    # Riesgos financieros del PredictionService (best-effort).
    try:
        rs = [r for r in F.riesgos(emp)
              if str(r.get("dominio", r.get("categoria", ""))).lower() in ("tesoreria", "financiero")]
        if rs:
            alertas += [r.get("texto") or r.get("descripcion") for r in rs[:3] if r.get("texto") or r.get("descripcion")]
            riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)
    except Exception:
        pass

    resumen = (f"Liquidez {round(disponible, 2)}; {cobros_pend} cobros y {pagos_pend} pagos "
               f"pendientes; {impagos} impagos.")
    return M.estado_dominio("financiero", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"posicion": pos})
