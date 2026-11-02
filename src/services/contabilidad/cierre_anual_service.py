"""
Orquestador de Cuentas Anuales — ensambla en un único dict las 6 piezas YA construidas
(`balance_situacion`, `ecpn`, `estado_flujos`, `memoria_anual`, `informe_gestion`,
`propuesta_resultado`) más el resultado de `cierre.validar_cierre`. NO calcula nada por sí
mismo: es pura composición, para que la GUI (`gui/contabilidad_gestion.py::_cerrar`) y el PDF
(`cuentas_anuales_pdf.generar_pdf_cuentas_anuales`) tengan un único punto de entrada en vez de
tener que conocer y llamar a los 7 módulos por separado.
"""

import logging

logger = logging.getLogger("contab.cierre_anual_service")


def generar_cuentas_anuales_completas(anio, id_empresa=None) -> dict:
    """Genera el paquete completo de Cuentas Anuales del ejercicio `anio`: balance, ecpn,
    estado_flujos, memoria, informe_gestion, propuesta y validacion (de `cierre.validar_cierre`).
    Cada pieza es best-effort: si una falla, queda como `None`/`{}` en el dict de salida y se
    loguea, pero no impide generar el resto (mismo criterio "no fatal" que el resto del módulo de
    cierre)."""
    anio = int(anio)
    out = {"anio": anio, "id_empresa": id_empresa}

    def _pieza(nombre, fn):
        try:
            return fn()
        except Exception as e:
            logger.error("generar_cuentas_anuales_completas: fallo en %s: %s", nombre, e)
            return None

    from src.services.contabilidad import balance_situacion as Bal
    from src.services.contabilidad import cierre as Ci
    from src.services.contabilidad import ecpn as Ecpn
    from src.services.contabilidad import estado_flujos as EF
    from src.services.contabilidad import informe_gestion as IG
    from src.services.contabilidad import memoria_anual as Mem
    from src.services.contabilidad import propuesta_resultado as PR

    out["balance"] = _pieza("balance", lambda: Bal.generar_balance(anio, id_empresa=id_empresa))
    out["ecpn"] = _pieza("ecpn", lambda: Ecpn.generar_ecpn(anio, id_empresa=id_empresa))
    out["estado_flujos"] = _pieza("estado_flujos",
                                  lambda: EF.generar_estado_flujos(anio, id_empresa=id_empresa))
    out["memoria"] = _pieza("memoria", lambda: Mem.generar_memoria(anio, id_empresa=id_empresa))
    out["informe_gestion"] = _pieza("informe_gestion",
                                    lambda: IG.generar_informe_gestion(anio, id_empresa=id_empresa))
    out["propuesta"] = _pieza("propuesta",
                              lambda: PR.calcular_propuesta_aplicacion(anio, id_empresa=id_empresa))
    out["validacion"] = _pieza("validacion", lambda: Ci.validar_cierre(anio, id_empresa=id_empresa))
    return out
