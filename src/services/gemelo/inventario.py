"""
Gemelo Digital de Inventario (Paquete Enterprise 8, SUBFASE 8.3). Representa en tiempo real:
stock, reservas, roturas, sobrestock, ubicaciones, movimientos, ultima actualizacion y riesgo.
Reutiliza PredictionService (riesgo de rotura/sobrestock) y los adaptadores de lectura de la IA;
no recalcula ni duplica el kardex.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)
    rot = exc = 0
    detalle = {}
    try:
        st = F.prediccion().stock(emp)
        detalle = st
        for p in st.get("predicciones", []):
            if p.get("metrica") == "rotura_stock":
                rot = int(p.get("valor") or 0)
            elif p.get("metrica") == "sobrestock":
                exc = int(p.get("valor") or 0)
    except Exception:
        pass

    # Bajo umbral / exceso via adaptadores de IA (misma condicion que el Informe de Reposicion).
    bajo = exceso = []
    try:
        from src.services.ia import adaptadores as A
        bajo = A.articulos_bajo_umbral(emp)
        exceso = A.articulos_exceso(emp)
    except Exception:
        pass

    # Reservas de stock: pedidos de cliente aun no servidos/facturados (proxy real de reserva).
    reservas = F.contar("SELECT COUNT(*) FROM ventas_pedidos_cliente WHERE id_empresa=%s "
                        "AND estado IN ('borrador','confirmado','pendiente','parcial')", (emp,))
    ultimo_mov = F.filas("SELECT MAX(fecha_movimiento) f FROM movimientos_stock WHERE id_empresa=%s", (emp,))
    ultima = (ultimo_mov[0].get("f") if ultimo_mov else None)

    ind = {
        "roturas_previstas": rot or len(bajo),
        "sobrestock_previsto": exc or len(exceso),
        "articulos_bajo_umbral": len(bajo),
        "articulos_exceso": len(exceso),
        "reservas_activas": reservas,
        "ultima_actualizacion": str(ultima) if ultima else None,
    }
    riesgo = M.RIESGO_BAJO
    if (rot or len(bajo)):
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_ALTO if (rot or len(bajo)) > 5 else M.RIESGO_MEDIO)
    if (exc or len(exceso)):
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)

    alertas = []
    if ind["roturas_previstas"]:
        alertas.append(f"{ind['roturas_previstas']} articulo(s) en riesgo de rotura")
    if ind["sobrestock_previsto"]:
        alertas.append(f"{ind['sobrestock_previsto']} articulo(s) con sobrestock")
    resumen = (f"Rotura: {ind['roturas_previstas']}; sobrestock: {ind['sobrestock_previsto']}; "
               f"reservas activas: {reservas}.")
    return M.estado_dominio("inventario", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"bajo_umbral": bajo[:20], "exceso": exceso[:20],
                                                      "prediccion": detalle})
