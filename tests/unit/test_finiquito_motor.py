"""
RRHH Fase Finiquito · Motor de finiquito (función pura). Tests unitarios SIN Qt/BD/PDF.

Verifica que `calcular_finiquito` reutiliza `nomina_motor.calcular_nomina` (nunca duplica la
aritmética de SS/IRPF: se contrasta contra una llamada equivalente directa al motor de nómina),
el prorrateo de días trabajados a 30 días, vacaciones no disfrutadas (sin negativos), pagas extra
pendientes y horas de bolsa pendientes.
"""

from src.rrhh.finiquito_motor import FiniquitoInput, calcular_finiquito
from src.rrhh.nomina_motor import NominaInput, calcular_nomina
from src.rrhh.parametros_cotizacion import cargar_parametros

P = cargar_parametros(2025)   # mismo recurso real que usan los tests de nomina_motor


def _calc(**kw):
    base = dict(salario_base_mensual=2000, dias_trabajados_periodo=30, grupo_cotizacion="1",
               irpf_tipo=15)
    base.update(kw)
    return calcular_finiquito(FiniquitoInput(**base), P)


# 1. Caso sencillo: salario conocido, mes completo trabajado, vacaciones pendientes conocidas,
#    sin deuda de bolsa de horas. El resultado debe coincidir EXACTAMENTE con llamar directamente
#    a `calcular_nomina` con un `NominaInput` equivalente (nunca se duplica esa aritmética).
def test_finiquito_simple_coincide_con_nomina_motor():
    r = _calc(dias_vacaciones_generados=10, dias_vacaciones_disfrutados=5,
              dias_vacaciones_reservados=0)

    assert r.dias_trabajados == 30
    assert r.vac_pendientes == 5.0
    # salario_diario = 2000/30; imp_vacaciones = 5 días * salario_diario
    assert r.imp_vacaciones == round(5 * (2000 / 30), 2)
    assert r.imp_salario_pendiente == 2000.0            # 30/30 días → salario íntegro, sin desfase
    assert r.imp_pagas == 0.0
    assert r.imp_horas_extras == 0.0

    equivalente = calcular_nomina(NominaInput(
        salario_base_mensual=2000.0, num_pagas=12, grupo_cotizacion="1",
        tipo_contrato="indefinido", irpf_tipo=15, pagas_extra_prorrateadas=False,
        vacaciones_compensadas=r.imp_vacaciones, pagas_extra_pendientes=0.0,
        horas_extra_bolsa_importe=0.0,
    ), P)
    assert r.total_bruto == equivalente.total_devengado
    assert r.total_liquido == equivalente.liquido
    assert r.desc_ss_trabajador == equivalente.ss_trabajador["total"]
    assert r.retencion_pct == equivalente.irpf_tipo
    # Coherencia interna: bruto - SS - IRPF == líquido
    assert round(r.total_bruto - r.desc_ss_trabajador
                 - equivalente.irpf_importe, 2) == r.total_liquido


# 2. Horas de bolsa pendientes de compensar por la empresa: se suman como devengo salarial propio
#    (mismo campo `horas_extra_bolsa_importe` que ya usa la nómina ordinaria para este concepto).
def test_finiquito_con_horas_bolsa_pendientes():
    sin_bolsa = _calc(dias_vacaciones_generados=0, dias_vacaciones_disfrutados=0,
                      importe_horas_bolsa=0.0)
    con_bolsa = _calc(dias_vacaciones_generados=0, dias_vacaciones_disfrutados=0,
                      importe_horas_bolsa=150.0)

    assert con_bolsa.imp_horas_extras == 150.0
    assert sin_bolsa.imp_horas_extras == 0.0
    # El bruto sube exactamente en el importe de horas de bolsa (mismo importe cotiza/tributa,
    # así que el líquido no sube en la misma cantidad — solo se comprueba que SÍ se incorpora).
    assert con_bolsa.total_bruto == round(sin_bolsa.total_bruto + 150.0, 2)
    assert con_bolsa.total_liquido > sin_bolsa.total_liquido


# 3. Vacaciones ya disfrutadas por encima (o igual) del derecho generado: pendientes debe quedar
#    en CERO, nunca negativo, y el cálculo no debe lanzar ningún error.
def test_finiquito_sin_vacaciones_pendientes_no_va_negativo():
    r = _calc(dias_vacaciones_generados=8, dias_vacaciones_disfrutados=8,
              dias_vacaciones_reservados=0)
    assert r.vac_pendientes == 0.0
    assert r.imp_vacaciones == 0.0

    r2 = _calc(dias_vacaciones_generados=5, dias_vacaciones_disfrutados=6,
               dias_vacaciones_reservados=2)   # disfrutadas+reservadas > generadas
    assert r2.vac_pendientes == 0.0
    assert r2.imp_vacaciones == 0.0


# 4. Pagas extra pendientes (contrato que NO las prorratea mensualmente): se suman igual que las
#    vacaciones, como devengo salarial que cotiza y tributa.
def test_finiquito_con_pagas_extra_pendientes():
    r = _calc(dias_vacaciones_generados=0, dias_vacaciones_disfrutados=0,
              importe_pagas_extra_pendientes=500.0)
    assert r.imp_pagas == 500.0
    assert r.total_bruto == round(2000.0 + 500.0, 2)


# 5. Días trabajados del período: se acota siempre a 30 (mismo criterio AJUSTE_A_30_DIAS que usa
#    la reducción por IT en `nomina_motor`) y nunca puede ser negativo.
def test_finiquito_dias_trabajados_se_acota_a_30():
    r = _calc(dias_trabajados_periodo=31, dias_vacaciones_generados=0,
              dias_vacaciones_disfrutados=0)
    assert r.dias_trabajados == 30
    assert r.imp_salario_pendiente == 2000.0


# 6. Salario base en cero (dato defensivo): no debe lanzar ZeroDivisionError ni ningún otro error.
def test_finiquito_salario_cero_no_lanza_error():
    r = _calc(salario_base_mensual=0, dias_vacaciones_generados=3, dias_vacaciones_disfrutados=0)
    assert r.imp_salario_pendiente == 0.0
    assert r.imp_vacaciones == 0.0        # salario_diario=0 → no puede valorar los días pendientes
    assert r.vac_pendientes == 3.0        # el SALDO de días sí se mantiene correcto
