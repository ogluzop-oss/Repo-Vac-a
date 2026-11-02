"""
Fase F.4 · Motor de Incapacidad Temporal (`src/rrhh/incapacidad_temporal.py`). Tests unitarios
puros (sin BD/Qt). Los 4 casos exigidos por el usuario, con el "muestra tu trabajo" de cada
número esperado en los comentarios.
"""

import datetime as _dt

from src.rrhh.incapacidad_temporal import (
    CONTINGENCIAS_COMUNES,
    CONTINGENCIAS_PROFESIONALES,
    ConfiguracionComplementoConvenio,
    calcular_it,
)


# ────────────────────────────────────────────────────────────────────────────────
# Caso 1 · Baja común de 7 días en un mes de 30 días (abril), con y sin complemento
#          de convenio al 100%.
#
# Datos comunes: salario_base_mensual = 3000 €  → salario_diario = 3000/30 = 100 €
#                base_cotizacion_mes_anterior = 3000 € → BRD = 3000/30 = 100 €
#                baja: 2024-04-01 .. 2024-04-07 (7 días, CONTINGENCIAS_COMUNES)
#
# Tramos (día ACUMULADO desde el inicio de la baja, que aquí coincide con el mes):
#   día 1-3  → 0%                         → 0,00 €/día × 3 = 0,00 €   (sin_prestacion)
#   día 4-7  → 60% BRD, a cargo EMPRESA   → 100*0.60=60,00 €/día × 4 = 240,00 €
#
# Ajuste a 30 días: dias_trabajados = 30 - 7 = 23
#   importe_salario_base_reducido = (3000/30) * 23 = 100 * 23 = 2300,00 €
#
# SIN complemento: total_devengado_bruto = 2300,00 + 240,00 = 2540,00 €
# ────────────────────────────────────────────────────────────────────────────────
def test_caso1_baja_comun_7_dias_sin_complemento():
    r = calcular_it(
        salario_base_mensual=3000.0,
        base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=0.0,
        fecha_inicio_baja=_dt.date(2024, 4, 1),
        fecha_fin_baja=_dt.date(2024, 4, 7),
        anio=2024, mes=4,
        tipo_contingencia=CONTINGENCIAS_COMUNES,
    )
    assert r.dias_it_en_mes == 7
    assert r.dias_trabajados_efectivos == 23
    assert r.importe_salario_base_reducido == 2300.0
    assert r.prestacion_it_empresa == 240.0          # 4 días × 60 €
    assert r.prestacion_it_pago_delegado == 0.0       # no llega al día 16
    assert r.complemento_convenio_it == 0.0
    assert r.total_devengado_bruto == 2540.0
    # Desglose: 3 días sin prestación + 4 días al 60% a cargo de la empresa.
    sin_prestacion = [d for d in r.desglose_por_tramos if d["pagador"] == "sin_prestacion"]
    empresa = [d for d in r.desglose_por_tramos if d["pagador"] == "empresa"]
    assert len(sin_prestacion) == 3 and len(empresa) == 4
    assert all(d["porcentaje"] == 0.0 for d in sin_prestacion)
    assert all(d["porcentaje"] == 60.0 and d["importe"] == 60.0 for d in empresa)


# ────────────────────────────────────────────────────────────────────────────────
# Caso 1b · Mismo escenario CON complemento de convenio al 100% (porcentaje_hasta,
# tramo días 1-999 → cubre toda la baja).
#
#   complemento_dia = max(0, BRD*100% - prestacion_legal_dia)
#   días 1-3: max(0, 100 - 0)  = 100,00 €/día × 3 = 300,00 €
#   días 4-7: max(0, 100 - 60) =  40,00 €/día × 4 = 160,00 €
#   complemento_convenio_it total = 300 + 160 = 460,00 €
#
# total_devengado_bruto = 2300,00 (reducido) + 240,00 (empresa) + 460,00 (complemento)
#                        = 3000,00 €
# Verificación de coherencia: con complemento al 100% el total coincide EXACTAMENTE con
# el salario mensual íntegro (3000 €) — el complemento rellena exactamente el hueco hasta
# el 100% de la base diaria en los días de baja, así que el trabajador no pierde nada.
# ────────────────────────────────────────────────────────────────────────────────
def test_caso1_baja_comun_7_dias_con_complemento_100pct():
    conf = ConfiguracionComplementoConvenio(
        activo=True, tipo="porcentaje_hasta", porcentaje=100.0,
        tramo_dias_inicio=1, tramo_dias_fin=999,
    )
    r = calcular_it(
        salario_base_mensual=3000.0,
        base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=0.0,
        fecha_inicio_baja=_dt.date(2024, 4, 1),
        fecha_fin_baja=_dt.date(2024, 4, 7),
        anio=2024, mes=4,
        tipo_contingencia=CONTINGENCIAS_COMUNES,
        configuracion_complemento_convenio=conf,
    )
    assert r.complemento_convenio_it == 460.0
    assert r.total_devengado_bruto == 3000.0


# ────────────────────────────────────────────────────────────────────────────────
# Caso 2 · Baja común que cruza del día 25 de un mes (enero) al día 10 del siguiente
#          (febrero) — el contador de día ACUMULADO del proceso no debe reiniciarse.
#
# Datos: salario_base_mensual = 3000 € (salario_diario = 100 €); BRD = 100 €.
# Baja real: 2024-01-25 .. 2024-02-10 (fecha_inicio_baja SIEMPRE 2024-01-25 en ambas
# llamadas, para que el día acumulado no se reinicie en febrero).
#
# ENERO (recorte al mes: 25-31 enero → 7 días, día acumulado 1..7):
#   día 1-3 (25,26,27 ene) → 0%
#   día 4-7 (28,29,30,31 ene) → 60% empresa → 4 × 60 = 240,00 €
#   dias_trabajados = 30 - 7 = 23 → importe_salario_base_reducido = 100*23 = 2300,00 €
#   total enero = 2300 + 240 = 2540,00 €
#
# FEBRERO (recorte al mes: 1-10 feb → 10 días, día acumulado CONTINÚA en 8..17 —
#          NO se reinicia a 1):
#   día 8-15 (1-8 feb, 8 días) → ≤15 → 60% EMPRESA → 8 × 60 = 480,00 €
#   día 16-17 (9-10 feb, 2 días) → 60% PAGO DELEGADO → 2 × 60 = 120,00 €
#   dias_trabajados = 30 - 10 = 20 → importe_salario_base_reducido = 100*20 = 2000,00 €
#   total febrero = 2000 + 480 + 120 = 2600,00 €
#
# Si el contador se hubiese reiniciado incorrectamente en febrero, los días 1-3 de
# febrero (que en realidad son el día acumulado 8-10 del proceso) habrían caído
# erróneamente en el tramo "0% sin prestación" — este test falla en ese caso.
# ────────────────────────────────────────────────────────────────────────────────
def test_caso2_cruce_de_mes_no_reinicia_contador():
    fecha_inicio = _dt.date(2024, 1, 25)
    fecha_fin = _dt.date(2024, 2, 10)

    r_enero = calcular_it(
        salario_base_mensual=3000.0, base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=0.0,
        fecha_inicio_baja=fecha_inicio, fecha_fin_baja=fecha_fin,
        anio=2024, mes=1, tipo_contingencia=CONTINGENCIAS_COMUNES,
    )
    assert r_enero.dias_it_en_mes == 7
    assert r_enero.dias_trabajados_efectivos == 23
    assert r_enero.importe_salario_base_reducido == 2300.0
    assert r_enero.prestacion_it_empresa == 240.0
    assert r_enero.prestacion_it_pago_delegado == 0.0
    assert r_enero.total_devengado_bruto == 2540.0
    # Último día de enero recortado = día acumulado 7 (31 ene = 25+6 → día 7).
    assert r_enero.desglose_por_tramos[-1]["dia_acumulado"] == 7

    r_febrero = calcular_it(
        salario_base_mensual=3000.0, base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=0.0,
        fecha_inicio_baja=fecha_inicio, fecha_fin_baja=fecha_fin,
        anio=2024, mes=2, tipo_contingencia=CONTINGENCIAS_COMUNES,
    )
    assert r_febrero.dias_it_en_mes == 10
    assert r_febrero.dias_trabajados_efectivos == 20
    assert r_febrero.importe_salario_base_reducido == 2000.0
    # El día acumulado del primer día de febrero DEBE continuar en 8, no reiniciarse a 1.
    primer_dia_feb = r_febrero.desglose_por_tramos[0]
    assert primer_dia_feb["fecha"] == _dt.date(2024, 2, 1)
    assert primer_dia_feb["dia_acumulado"] == 8
    assert primer_dia_feb["porcentaje"] == 60.0
    assert primer_dia_feb["pagador"] == "empresa"
    assert r_febrero.prestacion_it_empresa == 480.0     # días acumulados 8-15 (8 días)
    assert r_febrero.prestacion_it_pago_delegado == 120.0  # días acumulados 16-17 (2 días)
    assert r_febrero.total_devengado_bruto == 2600.0


# ────────────────────────────────────────────────────────────────────────────────
# Caso 3 · Baja por accidente laboral (CONTINGENCIAS_PROFESIONALES) de 5 días.
#
# Datos: salario_base_mensual = 3000 € → salario_diario = 100 €.
#        base_cotizacion_cp_mes_anterior = 3200 € → BRD_cp = 3200/30 = 106,6666... €
#        Baja: 2024-05-01 .. 2024-05-05 (5 días, dentro de un único mes de 31 días).
#
#   día 1 → 100% salario ordinario, EMPRESA → 100,00 €
#   días 2-5 (4 días) → 75% BRD_cp = (3200/30)*0.75 = 3200*3/(30*4) = 9600/120 = 80,00 €/día
#                       → 4 × 80,00 = 320,00 € (PAGO DELEGADO)
#
# Ajuste a 30 días: dias_trabajados = 30 - 5 = 25 → importe_salario_base_reducido = 100*25
#                    = 2500,00 €
#
# total_devengado_bruto = 2500,00 + 100,00 (empresa) + 320,00 (pago delegado) = 2920,00 €
# ────────────────────────────────────────────────────────────────────────────────
def test_caso3_accidente_laboral_5_dias():
    r = calcular_it(
        salario_base_mensual=3000.0,
        base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=3200.0,
        fecha_inicio_baja=_dt.date(2024, 5, 1),
        fecha_fin_baja=_dt.date(2024, 5, 5),
        anio=2024, mes=5,
        tipo_contingencia=CONTINGENCIAS_PROFESIONALES,
    )
    assert r.dias_it_en_mes == 5
    assert r.dias_trabajados_efectivos == 25
    assert r.importe_salario_base_reducido == 2500.0
    assert r.prestacion_it_empresa == 100.0            # día 1: 100% salario ordinario
    assert r.prestacion_it_pago_delegado == 320.0       # días 2-5: 4 × 80,00 €
    assert r.total_devengado_bruto == 2920.0
    dia1 = r.desglose_por_tramos[0]
    assert dia1["porcentaje"] == 100.0 and dia1["pagador"] == "empresa" and dia1["importe"] == 100.0
    dia2 = r.desglose_por_tramos[1]
    assert dia2["porcentaje"] == 75.0 and dia2["pagador"] == "pago_delegado" and dia2["importe"] == 80.0


# ────────────────────────────────────────────────────────────────────────────────
# Caso 4 · Meses de 31 días (enero) y febrero (28 días, 2023 no bisiesto), frente a un
# mes de 30 días (abril), confirmando que el devengo SIEMPRE respeta los 30 días
# teóricos con independencia de la duración real del mes.
#
# Misma baja (10 días, CONTINGENCIAS_COMUNES, empezando el día 1 de cada mes) replicada
# en los 3 meses — deben dar EXACTAMENTE el mismo resultado pese a que el mes natural
# tiene 31 / 28 / 30 días reales.
#
#   Tramos (día acumulado 1-10): día 1-3 → 0%; día 4-10 (7 días) → 60% empresa.
#   prestacion_it_empresa = 7 × 60,00 = 420,00 €
#   dias_trabajados = 30 - 10 = 20 → importe_salario_base_reducido = 100*20 = 2000,00 €
#   total_devengado_bruto = 2000,00 + 420,00 = 2420,00 €  (en LOS TRES meses, idéntico)
# ────────────────────────────────────────────────────────────────────────────────
def test_caso4_ajuste_30_dias_independiente_del_mes_real():
    escenarios = [
        (2024, 1, 31),   # enero: 31 días naturales
        (2023, 2, 28),   # febrero no bisiesto: 28 días naturales
        (2024, 4, 30),   # abril: 30 días naturales (caso "neutro")
    ]
    resultados = []
    for anio, mes, dias_reales_esperados in escenarios:
        import calendar as _cal
        assert _cal.monthrange(anio, mes)[1] == dias_reales_esperados
        r = calcular_it(
            salario_base_mensual=3000.0,
            base_cotizacion_mes_anterior=3000.0,
            base_cotizacion_cp_mes_anterior=0.0,
            fecha_inicio_baja=_dt.date(anio, mes, 1),
            fecha_fin_baja=_dt.date(anio, mes, 10),
            anio=anio, mes=mes,
            tipo_contingencia=CONTINGENCIAS_COMUNES,
        )
        resultados.append(r)
        assert r.dias_it_en_mes == 10
        # SIEMPRE 30 - 10 = 20, independientemente de que el mes real tenga 28/30/31 días.
        assert r.dias_trabajados_efectivos == 20
        assert r.importe_salario_base_reducido == 2000.0
        assert r.prestacion_it_empresa == 420.0
        assert r.total_devengado_bruto == 2420.0

    # Los 3 meses (31/28/30 días reales) producen EXACTAMENTE el mismo devengo.
    totales = {r.total_devengado_bruto for r in resultados}
    reducidos = {r.importe_salario_base_reducido for r in resultados}
    assert totales == {2420.0}
    assert reducidos == {2000.0}

    # Contraste explícito con la regla alternativa DIAS_NATURALES (no es la que usa la
    # nómina por defecto): en abril (30 días reales) coincide con el ajuste a 30; en
    # enero (31 días reales) el importe reducido es DISTINTO, porque sí depende del mes.
    from src.rrhh.incapacidad_temporal import DIAS_NATURALES
    r_enero_natural = calcular_it(
        salario_base_mensual=3000.0, base_cotizacion_mes_anterior=3000.0,
        base_cotizacion_cp_mes_anterior=0.0,
        fecha_inicio_baja=_dt.date(2024, 1, 1), fecha_fin_baja=_dt.date(2024, 1, 10),
        anio=2024, mes=1, tipo_contingencia=CONTINGENCIAS_COMUNES,
        regla_ajuste_mensual=DIAS_NATURALES,
    )
    # dias_trabajados = 31 - 10 = 21 → (3000/31)*21 = 2032.258... → redondeado 2032.26
    assert r_enero_natural.dias_trabajados_efectivos == 21
    assert r_enero_natural.importe_salario_base_reducido != 2000.0
