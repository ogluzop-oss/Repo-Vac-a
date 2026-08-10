"""
Gemelo Digital de RRHH (Paquete Enterprise 8, SUBFASE 8.5). Representa: empleados, contratos,
vacaciones, ausencias, delegaciones, aprobaciones, turnos y estado operativo. Reutiliza
PredictionService (contratos por vencer), Gobierno Corporativo (delegaciones) y consultas de
solo lectura; no duplica el modulo RRHH.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)

    empleados = F.contar("SELECT COUNT(*) FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
    contratos_activos = F.contar("SELECT COUNT(*) FROM rrhh_contratos WHERE id_empresa=%s "
                                 "AND (fecha_fin IS NULL OR fecha_fin >= CURDATE())", (emp,))
    contratos_venc = F.contar("SELECT COUNT(*) FROM rrhh_contratos WHERE id_empresa=%s "
                              "AND fecha_fin IS NOT NULL AND fecha_fin BETWEEN CURDATE() "
                              "AND (CURDATE() + INTERVAL 30 DAY)", (emp,))
    ausencias = F.contar("SELECT COUNT(*) FROM rrhh_ausencias WHERE id_empresa=%s "
                         "AND CURDATE() BETWEEN fecha_inicio AND fecha_fin", (emp,))

    delegaciones = F.delegaciones_activas(emp)

    ind = {
        "empleados": empleados,
        "contratos_activos": contratos_activos,
        "contratos_por_vencer": contratos_venc,
        "ausencias_hoy": ausencias,
        "delegaciones_activas": len(delegaciones),
    }
    riesgo = M.RIESGO_BAJO
    alertas = []
    if contratos_venc:
        alertas.append(f"{contratos_venc} contrato(s) por vencer (30 dias)")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)
    if ausencias:
        alertas.append(f"{ausencias} ausencia(s) en curso")

    resumen = (f"{empleados} empleados, {contratos_activos} contratos activos; "
               f"{contratos_venc} por vencer; {len(delegaciones)} delegaciones activas.")
    return M.estado_dominio("rrhh", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"delegaciones": delegaciones})
