"""
Motor de FINIQUITO (liquidación de saldo y finiquito) — función PURA (RRHH Fase Finiquito).

`calcular_finiquito(entrada, parametros) -> FiniquitoResultado`. Sin Qt, sin BD, sin `self`, sin
globales: depende SOLO de `FiniquitoInput` y `nomina_motor.ParametrosAnio`. Determinista.

Reutiliza `nomina_motor.calcular_nomina` para TODA la parte "salarial ordinaria" del finiquito
(salario proporcional a los días trabajados del último periodo + horas de bolsa pendientes +
vacaciones no disfrutadas + pagas extra pendientes) — estos cuatro conceptos son, a efectos de
Seguridad Social e IRPF, devengo salarial ORDINARIO (cotizan BCCC/BCCP y tributan exactamente
igual que un salario), así que se combinan en UN ÚNICO `NominaInput`/`calcular_nomina` para que
los topes de cotización (tope_max/tope_min) y el tipo de IRPF se apliquen sobre la base COMBINADA
correcta — nunca se reimplementa esa aritmética de SS/IRPF aquí.

Fuera de alcance deliberado (quedan como importes editables por el usuario en el formulario, NO
se auto-calculan): indemnización (depende del tipo/causa legal de la extinción, exenta de IRPF
hasta el límite legal — cálculo fuera del alcance de esta fase), bonus/incentivos/comisiones,
anticipos/embargos/otros descuentos. El PDF (`documents/render/finiquito_pdf.py`) sigue sumando
esos importes manuales junto a los aquí calculados sin ningún cambio en su lógica.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rrhh.nomina_motor import NominaInput, ParametrosAnio, calcular_nomina


def _r(x) -> float:
    return round(float(x or 0), 2)


@dataclass
class FiniquitoInput:
    # Salario del período final (mensual "fijo" YA resuelto, o ya calculado a partir de
    # horas × tarifa si el contrato es por horas) — SIN reducir a los días trabajados: la
    # reducción a `dias_trabajados_periodo` la hace `calcular_finiquito`.
    salario_base_mensual: float
    dias_trabajados_periodo: int             # días naturales trabajados del último mes (1-30)
    grupo_cotizacion: str = "7"
    tipo_contrato: str = "indefinido"
    irpf_tipo: float | None = None
    # Vacaciones (días; ver `finiquito_servicio` para el origen/prorrateo de `generados`)
    dias_vacaciones_generados: float = 0.0
    dias_vacaciones_disfrutados: float = 0.0
    dias_vacaciones_reservados: float = 0.0   # solicitudes ya aprobadas/pendientes que descuentan saldo
    # Pagas extra devengadas y no cobradas (0 si el contrato ya las prorratea mensualmente —
    # ver `finiquito_servicio`, que documenta la suposición por defecto)
    importe_pagas_extra_pendientes: float = 0.0
    # Horas de bolsa de horas pendientes de compensar por la EMPRESA, YA valoradas en euros
    importe_horas_bolsa: float = 0.0


@dataclass
class FiniquitoResultado:
    # Detalle informativo (días/unidades) — claves listas para `finiquito_pdf.DETALLE_CAMPOS`
    dias_trabajados: int = 0
    vac_generadas: float = 0.0
    vac_disfrutadas: float = 0.0
    vac_pendientes: float = 0.0
    # Conceptos devengados (importes) — claves listas para `finiquito_pdf.CONCEPTOS_IMPORTE`
    imp_salario_pendiente: float = 0.0
    imp_vacaciones: float = 0.0
    imp_pagas: float = 0.0
    imp_horas_extras: float = 0.0
    # Deducciones/retención derivadas del motor de nómina reutilizado
    retencion_pct: float = 0.0
    desc_ss_trabajador: float = 0.0
    # Totales del bloque AUTO-calculado únicamente (el PDF vuelve a sumar todo, incluidos los
    # importes manuales — indemnización/bonus/anticipos/etc. — que este resultado no conoce)
    total_bruto: float = 0.0
    total_liquido: float = 0.0
    meta: dict = field(default_factory=dict)


def calcular_finiquito(entrada: FiniquitoInput, parametros: ParametrosAnio) -> FiniquitoResultado:
    e = entrada
    # Sin redondear el intermedio (mismo criterio que la reducción por IT de `nomina_motor`: solo
    # se redondea el resultado final, nunca la tarifa/día) — evita un desfase de céntimos cuando
    # `dias_trab` cubre el mes completo (30/30 debe dar EXACTAMENTE el salario mensual íntegro).
    salario_diario = (e.salario_base_mensual / 30) if e.salario_base_mensual else 0.0
    # Ajuste a 30 días (mismo criterio que la reducción por IT de `nomina_motor`, regla
    # AJUSTE_A_30_DIAS): un mes "natural" de nómina se trata siempre como 30 días.
    dias_trab = max(0, min(int(e.dias_trabajados_periodo or 0), 30))
    salario_pendiente = _r(salario_diario * dias_trab)

    vac_pendientes = _r(max(0.0, _r(e.dias_vacaciones_generados) - _r(e.dias_vacaciones_disfrutados)
                            - _r(e.dias_vacaciones_reservados)))
    imp_vacaciones = _r(vac_pendientes * salario_diario)

    ni = NominaInput(
        salario_base_mensual=salario_pendiente,
        num_pagas=12,                        # el prorrateo de extras no aplica aquí (ver docstring)
        grupo_cotizacion=e.grupo_cotizacion,
        tipo_contrato=e.tipo_contrato,
        irpf_tipo=e.irpf_tipo,
        pagas_extra_prorrateadas=False,
        horas_extra_bolsa_importe=_r(e.importe_horas_bolsa),
        vacaciones_compensadas=imp_vacaciones,
        pagas_extra_pendientes=_r(e.importe_pagas_extra_pendientes),
    )
    res_motor = calcular_nomina(ni, parametros)

    return FiniquitoResultado(
        dias_trabajados=dias_trab,
        vac_generadas=_r(e.dias_vacaciones_generados),
        vac_disfrutadas=_r(e.dias_vacaciones_disfrutados),
        vac_pendientes=vac_pendientes,
        imp_salario_pendiente=salario_pendiente,
        imp_vacaciones=imp_vacaciones,
        imp_pagas=_r(e.importe_pagas_extra_pendientes),
        imp_horas_extras=_r(e.importe_horas_bolsa),
        retencion_pct=res_motor.irpf_tipo,
        desc_ss_trabajador=res_motor.ss_trabajador.get("total", 0.0),
        total_bruto=res_motor.total_devengado,
        total_liquido=res_motor.liquido,
        meta={"nomina_resultado": res_motor},
    )
