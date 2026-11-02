"""
Calculadora Fiscal (Contabilidad) — estimación del Impuesto de Sociedades y del ahorro fiscal
derivado de deducciones (contratación, I+D, digitalización).

`simular()` NO es 100% pura desde la Fase 2 (necesita consultar las reglas editables de
`fiscal_is_reglas`), pero sigue sin decidir NADA por su cuenta: los tipos/deducciones vienen siempre
de `fiscal_is_reglas.resolver()` (reglas editables desde la propia pantalla de la Calculadora Fiscal,
nunca de un fichero). Si un concepto no tiene ninguna regla aplicable, NO se inventa un valor: se
reporta en `reglas_faltantes` para que la GUI lo muestre. `datos_reales_sugeridos()`/`desglose_b2b()`
acceden a BD SOLO para prellenar/informar — nunca deciden el resultado del cálculo por su cuenta.

Estimación orientativa, sujeta a validación de un asesor fiscal antes de un uso real.
"""

import datetime as _dt
import logging

logger = logging.getLogger("contab.calculadora_fiscal")


def _empresa(id_empresa=None):
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID


_NOTA_LEGAL = ("Estimación basada en las reglas fiscales configuradas en el sistema (editables desde "
              "«Parámetros fiscales» en esta misma pantalla) y en la normativa general del Impuesto "
              "de Sociedades. No sustituye el asesoramiento de un asesor fiscal. Validar siempre antes "
              "de presentar cualquier declaración ante la Agencia Tributaria.")

# País Vasco/Navarra tienen normativa FORAL propia (Concierto/Convenio Económico) — un tipo/deducción
# distintos de la general, gestionados por sus propias Diputaciones/Hacienda Foral, no por este
# cálculo salvo que el usuario haya dado de alta sus propias reglas con esa `ccaa`.
CCAA_FORALES = ("País Vasco", "Comunidad Foral de Navarra")


def _valor_regla(concepto, *, ccaa, tipo_entidad, base_imponible, fecha, id_empresa):
    from src.services.contabilidad import fiscal_is_reglas as R
    regla = R.resolver(concepto, ccaa=ccaa, tipo_entidad=tipo_entidad, base_imponible=base_imponible,
                       fecha=fecha, id_empresa=id_empresa)
    return regla


def simular(*, ingresos_brutos=0.0, gastos_operativos=0.0, num_empleados_total=0,
           nuevas_contrataciones_indefinidas=0, contrataciones_bonificadas=0,
           inversion_id=0.0, inversion_digitalizacion=0.0, ccaa=None, tipo_entidad=None,
           fecha=None, id_empresa=None, deducciones_aceptadas=None) -> dict:
    """Estimación del Impuesto de Sociedades y sus deducciones, resolviendo cada tipo/deducción contra
    `fiscal_is_reglas` (editable desde la propia pantalla). Las deducciones nunca dejan la cuota en
    negativo (igual que en la ley real, no generan devolución). Si algún concepto no tiene ninguna
    regla aplicable, no se inventa un valor: queda en `reglas_faltantes`.

    `deducciones_aceptadas`: opcional, lista de deducciones sectoriales aceptadas por el usuario en
    el Paso 3 de la Calculadora Fiscal (`gui/calculadora_fiscal_wizard.py`), shape
    `{'concepto','tipo','importe'}` (mismo idioma que `aeat.modelo_130`, clasificadas con
    `fiscal_deducciones.separar_por_tipo`). Las de tipo 'gasto' se suman a `gastos_operativos` antes
    de calcular la base imponible; las de tipo 'cuota' restan del `impuesto_final` ya calculado.
    Omitido/None/vacío produce el MISMO resultado que antes de esta integración."""
    from src.services.contabilidad.fiscal_deducciones import separar_por_tipo
    fecha = fecha or _dt.date.today()
    ded_gasto, ded_cuota = separar_por_tipo(deducciones_aceptadas)
    ingresos = max(0.0, float(ingresos_brutos or 0))
    gastos = max(0.0, float(gastos_operativos or 0)) + ded_gasto
    base_imponible = round(max(0.0, ingresos - gastos), 2)

    faltantes = []

    def _regla(concepto):
        r = _valor_regla(concepto, ccaa=ccaa, tipo_entidad=tipo_entidad, base_imponible=base_imponible,
                         fecha=fecha, id_empresa=id_empresa)
        if r is None:
            faltantes.append(concepto)
            return 0.0
        return float(r["valor"])

    tipo = _regla("tipo_general")
    cuota_integra = round(base_imponible * tipo / 100, 2)

    nuevas_indef = max(0, int(nuevas_contrataciones_indefinidas or 0))
    bonificadas = max(0, int(contrataciones_bonificadas or 0))
    valor_indef = _regla("empleo_indefinido") if nuevas_indef else 0.0
    valor_bonif = _regla("empleo_bonificado") if bonificadas else 0.0
    deduccion_empleo = round(nuevas_indef * valor_indef + bonificadas * valor_bonif, 2)

    inv_id = max(0.0, float(inversion_id or 0))
    inv_dig = max(0.0, float(inversion_digitalizacion or 0))
    pct_id = _regla("id") if inv_id else 0.0
    pct_dig = _regla("digitalizacion") if inv_dig else 0.0
    deduccion_id = round(inv_id * pct_id / 100, 2)
    deduccion_digitalizacion = round(inv_dig * pct_dig / 100, 2)

    deducciones_solicitadas = round(deduccion_empleo + deduccion_id + deduccion_digitalizacion, 2)
    total_deducciones = round(min(cuota_integra, deducciones_solicitadas), 2)
    impuesto_final = round(cuota_integra - total_deducciones, 2)
    # Deducciones sectoriales de tipo 'cuota' (crédito fiscal directo, ver docstring) — igual que las
    # deducciones ordinarias de arriba, nunca dejan el impuesto final en negativo.
    impuesto_final = max(0.0, round(impuesto_final - ded_cuota, 2))

    return {
        "base_imponible": base_imponible,
        "tipo_general_pct": tipo,
        "cuota_integra": cuota_integra,
        "deduccion_empleo": deduccion_empleo,
        "deduccion_id": deduccion_id,
        "deduccion_digitalizacion": deduccion_digitalizacion,
        "deducciones_solicitadas": deducciones_solicitadas,
        "total_deducciones": total_deducciones,
        "topado": deducciones_solicitadas > cuota_integra,
        "impuesto_final": impuesto_final,
        # Incluye el crédito fiscal sectorial (tipo 'cuota') además de las deducciones ordinarias:
        # cuando no hay ninguna deducción de ese tipo aceptada (ded_cuota=0.0, el caso de hoy y el
        # caso por defecto), este valor es IDÉNTICO al de antes de esta integración.
        "ahorro_fiscal_estimado": round(total_deducciones + ded_cuota, 2),
        "deducciones_sectoriales_gasto": ded_gasto,
        "deducciones_sectoriales_cuota": ded_cuota,
        "num_empleados_total": max(0, int(num_empleados_total or 0)),
        "ccaa": ccaa,
        "tipo_entidad": tipo_entidad,
        "reglas_faltantes": faltantes,
        "aviso_foral": bool(ccaa and ccaa in CCAA_FORALES),
        "nota_legal": _NOTA_LEGAL,
    }


def _edad(fecha_nacimiento, hoy):
    if not fecha_nacimiento:
        return None
    try:
        fn = fecha_nacimiento if isinstance(fecha_nacimiento, _dt.date) else \
            _dt.date.fromisoformat(str(fecha_nacimiento)[:10])
    except Exception:
        return None
    return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))


UMBRAL_EDAD_BONIFICADA = 30
UMBRAL_DISCAPACIDAD_PCT = 33


def datos_reales_sugeridos(id_empresa=None, anio=None) -> dict:
    """Cifras reales para PRELLENAR el asistente (siempre editables después). Degrada a 0/None sin
    romper el asistente si Contabilidad o RRHH no están disponibles para esta empresa."""
    id_empresa = _empresa(id_empresa)
    hoy = _dt.date.today()
    anio_efectivo = int(anio) if anio else hoy.year
    salida = {"ingresos_brutos": None, "gastos_operativos": None, "num_empleados_total": None,
              "nuevas_contrataciones_indefinidas": None, "contrataciones_bonificadas": None}
    try:
        from src.services.contabilidad import informes
        pyg = informes.perdidas_ganancias(id_empresa, anio=anio)
        salida["ingresos_brutos"] = pyg.get("ingresos")
        salida["gastos_operativos"] = pyg.get("gastos")
    except Exception as e:
        logger.debug("datos_reales_sugeridos: pérdidas y ganancias no disponibles: %s", e)
    try:
        from src.rrhh.db.empleados import listar_empleados
        salida["num_empleados_total"] = len(listar_empleados(id_empresa, estado="activo"))
    except Exception as e:
        logger.debug("datos_reales_sugeridos: plantilla RRHH no disponible: %s", e)
    try:
        from src.rrhh.db.contratos import nuevas_altas_indefinidas
        altas = nuevas_altas_indefinidas(anio_efectivo, id_empresa)
        salida["nuevas_contrataciones_indefinidas"] = len(altas)
        salida["contrataciones_bonificadas"] = sum(
            1 for a in altas
            if (_edad(a.get("fecha_nacimiento"), hoy) or 999) < UMBRAL_EDAD_BONIFICADA
            or (a.get("discapacidad_pct") or 0) >= UMBRAL_DISCAPACIDAD_PCT)
    except Exception as e:
        logger.debug("datos_reales_sugeridos: altas de RRHH no disponibles: %s", e)
    return salida


def desglose_b2b(id_empresa=None) -> dict | None:
    """Desglose informativo de gasto B2B ya facturado este mes (`compras.b2b_presupuesto`). NO se
    suma al campo de Gastos Operativos: las compras B2B ya facturadas ya forman parte del total de
    `perdidas_ganancias()['gastos']` (vía el asiento de compra) — sumarlo de nuevo duplicaría el
    gasto. Se muestra solo como contexto ("de tus gastos, X€ ya son B2B")."""
    id_empresa = _empresa(id_empresa)
    try:
        from src.services.compras import b2b_presupuesto
        gasto_b2b_mes = b2b_presupuesto.gasto_validado_mes(id_empresa)
        return {"gasto_b2b_mes": gasto_b2b_mes}
    except Exception as e:
        logger.debug("desglose_b2b: no disponible: %s", e)
        return None
