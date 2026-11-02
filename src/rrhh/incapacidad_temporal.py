"""
Motor de Incapacidad Temporal (IT) — Fase F.4 del plan RRHH/nómina/bolsa de horas.

Módulo PURO (sin BD, sin Qt, sin `self` de negocio): calcula, para UN mes de liquidación
concreto (`anio`/`mes`), el desglose legal completo de una baja médica — sustituye el
prorrateo simplificado "horas_diarias × días de baja" por el cálculo real por tramos de
contingencia + ajuste a 30 días + complemento de convenio opcional.

Diseño clave para el "cruce de mes" (una baja que empieza en un mes y sigue en el
siguiente): el día ACUMULADO del proceso de IT (el que determina qué tramo/porcentaje
aplica) se deriva SIEMPRE de la fecha de inicio REAL de la baja
(`dia_acumulado = (fecha - fecha_inicio_baja).days + 1`), nunca de un contador que se
reinicia por mes — así que basta con invocar `calcular_it(...)` una vez por cada mes
natural que la baja atraviesa, pasando siempre la MISMA `fecha_inicio_baja` original; el
contador queda naturalmente continuo sin ningún estado explícito que mantener entre
llamadas.

Tramos por tipo de contingencia (especificados por el usuario, fuente única de verdad —
`tests/unit/test_incapacidad_temporal.py` los verifica con números calculados a mano):

  - CONTINGENCIAS_COMUNES: días 1-3 → 0% (sin prestación); días 4-15 → 60% BRD a cargo de
    la EMPRESA (pago delegado); días 16-20 → 60% BRD a cargo del INSS (pago delegado);
    día 21+ → 75% BRD a cargo del INSS (pago delegado).
  - CONTINGENCIAS_PROFESIONALES: día 1 → 100% del salario ordinario, a cargo de la
    EMPRESA; día 2+ → 75% de la BRD de CONTINGENCIAS PROFESIONALES (`base_cotizacion_cp_
    mes_anterior`), a cargo del INSS (pago delegado).
  - MENSTRUACION_INCAPACITANTE: días 1-20 → 60% BRD; día 21+ → 75% BRD — sin franquicia de
    días 1-3 (a diferencia de contingencias comunes) y a cargo del INSS desde el día 1
    (reforma Ley Orgánica 1/2023: no hay avance/pago delegado de la empresa).
  - INTERRUPCION_EMBARAZO_GESTACION: día 1 → 100% salario ordinario (EMPRESA, igual
    estructura que contingencias profesionales); días 2-20 → 60% BRD; día 21+ → 75% BRD
    (INSS, pago delegado).
  - NACIMIENTO_CUIDADO_MENOR: desde el día 1 → 100% BRD, PRESTACIÓN DIRECTA (ni empresa ni
    pago delegado — así lo especifica el usuario explícitamente).

Estos dos últimos repartos (menstruación/nacimiento) no vienen desglosados campo a campo
en la especificación del usuario más allá del porcentaje — la asignación de "pagador" se
documenta aquí explícitamente (no se oculta como una decisión silenciosa) siguiendo el
tratamiento legal real vigente de cada prestación.

Ajuste a 30 días (regla por defecto para mensuales, `AJUSTE_A_30_DIAS`):
  `dias_trabajados_efectivos = 30 - dias_it_en_mes` (nunca negativo) y
  `importe_salario_base_reducido = (salario_base_mensual / 30) * dias_trabajados_efectivos`
  — SIEMPRE sobre la base teórica de 30 días, con independencia de que el mes natural
  tenga 28, 29, 30 o 31 días. La alternativa `DIAS_NATURALES` (no es la que usa la nómina
  por defecto) prorratea sobre los días reales del mes, para quien la necesite.

Complemento de convenio (`configuracion_complemento_convenio`, opcional): solo dentro del
tramo de días configurado (`tramo_dias_inicio`/`tramo_dias_fin`, en día ACUMULADO),
`complemento_dia = max(0, BRD_comunes * pct/100 - prestacion_legal_dia)` cuando el tipo es
`porcentaje_hasta`; si el tipo es `importe_fijo`, el mismo campo `porcentaje` se interpreta
como un importe fijo en euros por día (no hay una columna de importe separada en
`rrhh_contratos` — decisión documentada, no oculta).
"""

from __future__ import annotations

import calendar as _calendar
import datetime as _dt
from dataclasses import dataclass, field

# ── Tipos de contingencia soportados ────────────────────────────────────────────
# (mismos valores que `rrhh_ausencias.tipo_contingencia` / `ausencias_servicio.
# TIPOS_CONTINGENCIA` — duplicados aquí a propósito, NO importados, para que este módulo
# sea 100% autónomo/puro y testeable sin tocar la capa de BD.)
CONTINGENCIAS_COMUNES = "CONTINGENCIAS_COMUNES"
CONTINGENCIAS_PROFESIONALES = "CONTINGENCIAS_PROFESIONALES"
MENSTRUACION_INCAPACITANTE = "MENSTRUACION_INCAPACITANTE"
INTERRUPCION_EMBARAZO_GESTACION = "INTERRUPCION_EMBARAZO_GESTACION"
NACIMIENTO_CUIDADO_MENOR = "NACIMIENTO_CUIDADO_MENOR"

TIPOS_CONTINGENCIA_VALIDOS = frozenset({
    CONTINGENCIAS_COMUNES, CONTINGENCIAS_PROFESIONALES, MENSTRUACION_INCAPACITANTE,
    INTERRUPCION_EMBARAZO_GESTACION, NACIMIENTO_CUIDADO_MENOR,
})

# ── Reglas de ajuste mensual ─────────────────────────────────────────────────────
AJUSTE_A_30_DIAS = "AJUSTE_A_30_DIAS"
DIAS_NATURALES = "DIAS_NATURALES"

# ── Pagadores (quién asume la prestación de cada día) ────────────────────────────
PAGADOR_EMPRESA = "empresa"
PAGADOR_PAGO_DELEGADO = "pago_delegado"
PAGADOR_DIRECTA = "directa"
PAGADOR_SIN_PRESTACION = "sin_prestacion"


class IncapacidadTemporalError(Exception):
    """Parámetros de entrada inválidos para el cálculo de IT."""


def _r(x) -> float:
    return round(float(x or 0), 2)


def _num_o_none(v):
    return None if v in (None, "") else float(v)


def _int_o_none(v):
    return None if v in (None, "") else int(v)


# ── Configuración del complemento de convenio (Fase A/B del contrato) ───────────
@dataclass(frozen=True)
class ConfiguracionComplementoConvenio:
    activo: bool = False
    tipo: str = "ninguno"              # 'porcentaje_hasta' | 'importe_fijo' | 'ninguno'
    porcentaje: float | None = None    # % (porcentaje_hasta) o importe €/día (importe_fijo)
    tramo_dias_inicio: int | None = None
    tramo_dias_fin: int | None = None

    @classmethod
    def desde_contrato(cls, contrato: dict | None) -> "ConfiguracionComplementoConvenio":
        """Construye la configuración a partir de las columnas `complemento_it_*` de
        `rrhh_contratos` (Fase A/B) — acepta directamente esa fila (o un subconjunto)."""
        c = contrato or {}
        return cls(
            activo=bool(c.get("complemento_it_activo")),
            tipo=str(c.get("complemento_it_tipo") or "ninguno"),
            porcentaje=_num_o_none(c.get("complemento_it_porcentaje")),
            tramo_dias_inicio=_int_o_none(c.get("complemento_it_tramo_dias_inicio")),
            tramo_dias_fin=_int_o_none(c.get("complemento_it_tramo_dias_fin")),
        )


@dataclass
class ResultadoIT:
    dias_trabajados_efectivos: int = 0
    dias_it_en_mes: int = 0
    importe_salario_base_reducido: float = 0.0
    prestacion_it_empresa: float = 0.0             # tramo día 4-15 en comunes / día 1 en profesionales
    prestacion_it_pago_delegado: float = 0.0        # día 16+ en comunes / día 2+ en profesionales
    prestacion_it_directa: float = 0.0              # NACIMIENTO_CUIDADO_MENOR: prestación directa
    complemento_convenio_it: float = 0.0
    total_devengado_bruto: float = 0.0
    desglose_por_tramos: list = field(default_factory=list)   # [{fecha, dia_acumulado, porcentaje,
                                                                #   pagador, importe, complemento}]


# ── Tabla de tramos (pura, por día ACUMULADO del proceso de IT) ─────────────────
def _tramo_dia(tipo_contingencia: str, dia_acumulado: int, brd_comun: float, brd_cp: float,
              salario_diario: float) -> tuple[float, float, str]:
    """Devuelve `(porcentaje_legal, importe_prestacion_legal_del_dia, pagador)` para UN día
    del proceso de IT. `dia_acumulado` es 1-indexado desde el inicio REAL de la baja
    (continuo entre meses — ver docstring del módulo)."""
    tc = tipo_contingencia

    if tc == CONTINGENCIAS_COMUNES:
        if dia_acumulado <= 3:
            return 0.0, 0.0, PAGADOR_SIN_PRESTACION
        if dia_acumulado <= 15:
            return 60.0, _r(brd_comun * 0.60), PAGADOR_EMPRESA
        if dia_acumulado <= 20:
            return 60.0, _r(brd_comun * 0.60), PAGADOR_PAGO_DELEGADO
        return 75.0, _r(brd_comun * 0.75), PAGADOR_PAGO_DELEGADO

    if tc == CONTINGENCIAS_PROFESIONALES:
        if dia_acumulado == 1:
            return 100.0, _r(salario_diario), PAGADOR_EMPRESA
        return 75.0, _r(brd_cp * 0.75), PAGADOR_PAGO_DELEGADO

    if tc == MENSTRUACION_INCAPACITANTE:
        if dia_acumulado <= 20:
            return 60.0, _r(brd_comun * 0.60), PAGADOR_PAGO_DELEGADO
        return 75.0, _r(brd_comun * 0.75), PAGADOR_PAGO_DELEGADO

    if tc == INTERRUPCION_EMBARAZO_GESTACION:
        if dia_acumulado == 1:
            return 100.0, _r(salario_diario), PAGADOR_EMPRESA
        if dia_acumulado <= 20:
            return 60.0, _r(brd_comun * 0.60), PAGADOR_PAGO_DELEGADO
        return 75.0, _r(brd_comun * 0.75), PAGADOR_PAGO_DELEGADO

    if tc == NACIMIENTO_CUIDADO_MENOR:
        return 100.0, _r(brd_comun * 1.00), PAGADOR_DIRECTA

    raise IncapacidadTemporalError(f"Tipo de contingencia no soportado: {tipo_contingencia!r}")


def calcular_it(
    *,
    salario_base_mensual: float,
    base_cotizacion_mes_anterior: float,
    base_cotizacion_cp_mes_anterior: float,
    fecha_inicio_baja: _dt.date,
    fecha_fin_baja: _dt.date,
    anio: int,
    mes: int,
    tipo_contingencia: str,
    regla_ajuste_mensual: str = AJUSTE_A_30_DIAS,
    configuracion_complemento_convenio: "ConfiguracionComplementoConvenio | dict | None" = None,
) -> ResultadoIT:
    """Calcula el devengo de IT para el mes natural `anio`/`mes`, recortando la baja
    `[fecha_inicio_baja, fecha_fin_baja]` a los días de ESE mes concreto. Se invoca una vez
    por cada mes que la baja atraviesa, pasando siempre la MISMA `fecha_inicio_baja` real
    (nunca la fecha recortada) para que el día acumulado del proceso no se reinicie."""
    if tipo_contingencia not in TIPOS_CONTINGENCIA_VALIDOS:
        raise IncapacidadTemporalError(f"tipo_contingencia no válido: {tipo_contingencia!r}")
    if fecha_inicio_baja > fecha_fin_baja:
        raise IncapacidadTemporalError("fecha_inicio_baja no puede ser posterior a fecha_fin_baja.")
    if regla_ajuste_mensual not in (AJUSTE_A_30_DIAS, DIAS_NATURALES):
        raise IncapacidadTemporalError(f"regla_ajuste_mensual no válida: {regla_ajuste_mensual!r}")

    if isinstance(configuracion_complemento_convenio, dict):
        conf = ConfiguracionComplementoConvenio.desde_contrato(configuracion_complemento_convenio)
    else:
        conf = configuracion_complemento_convenio or ConfiguracionComplementoConvenio()

    dias_mes_calendario = _calendar.monthrange(anio, mes)[1]
    primer_dia_mes = _dt.date(anio, mes, 1)
    ultimo_dia_mes = _dt.date(anio, mes, dias_mes_calendario)

    dia_ini = max(fecha_inicio_baja, primer_dia_mes)
    dia_fin = min(fecha_fin_baja, ultimo_dia_mes)
    dias_it_en_mes = (dia_fin - dia_ini).days + 1 if dia_ini <= dia_fin else 0

    salario_diario = _r(float(salario_base_mensual or 0) / 30)
    brd_comun = _r(float(base_cotizacion_mes_anterior or 0) / 30)
    brd_cp = _r(float(base_cotizacion_cp_mes_anterior or 0) / 30)

    if regla_ajuste_mensual == DIAS_NATURALES:
        dias_trabajados = max(0, dias_mes_calendario - dias_it_en_mes)
        base_diaria = (float(salario_base_mensual or 0) / dias_mes_calendario) if dias_mes_calendario else 0.0
        importe_salario_base_reducido = _r(base_diaria * dias_trabajados)
    else:
        dias_trabajados = max(0, 30 - dias_it_en_mes)
        importe_salario_base_reducido = _r(salario_diario * dias_trabajados)

    desglose = []
    prestacion_empresa = 0.0
    prestacion_delegado = 0.0
    prestacion_directa = 0.0
    complemento_total = 0.0

    dia = dia_ini
    while dias_it_en_mes and dia <= dia_fin:
        dia_acumulado = (dia - fecha_inicio_baja).days + 1
        pct, importe_legal, pagador = _tramo_dia(
            tipo_contingencia, dia_acumulado, brd_comun, brd_cp, salario_diario)

        complemento_dia = 0.0
        if conf.activo and conf.tipo != "ninguno":
            dentro_tramo = (
                (conf.tramo_dias_inicio is None or dia_acumulado >= conf.tramo_dias_inicio)
                and (conf.tramo_dias_fin is None or dia_acumulado <= conf.tramo_dias_fin)
            )
            if dentro_tramo:
                if conf.tipo == "porcentaje_hasta":
                    objetivo = _r(brd_comun * float(conf.porcentaje or 0) / 100)
                    complemento_dia = _r(max(0.0, objetivo - importe_legal))
                elif conf.tipo == "importe_fijo":
                    complemento_dia = _r(max(0.0, float(conf.porcentaje or 0)))

        if pagador == PAGADOR_EMPRESA:
            prestacion_empresa += importe_legal
        elif pagador == PAGADOR_PAGO_DELEGADO:
            prestacion_delegado += importe_legal
        elif pagador == PAGADOR_DIRECTA:
            prestacion_directa += importe_legal
        complemento_total += complemento_dia

        desglose.append({
            "fecha": dia, "dia_acumulado": dia_acumulado, "porcentaje": pct,
            "pagador": pagador, "importe": importe_legal, "complemento": complemento_dia,
        })
        dia += _dt.timedelta(days=1)

    prestacion_empresa = _r(prestacion_empresa)
    prestacion_delegado = _r(prestacion_delegado)
    prestacion_directa = _r(prestacion_directa)
    complemento_total = _r(complemento_total)
    total = _r(importe_salario_base_reducido + prestacion_empresa + prestacion_delegado
               + prestacion_directa + complemento_total)

    return ResultadoIT(
        dias_trabajados_efectivos=dias_trabajados,
        dias_it_en_mes=dias_it_en_mes,
        importe_salario_base_reducido=importe_salario_base_reducido,
        prestacion_it_empresa=prestacion_empresa,
        prestacion_it_pago_delegado=prestacion_delegado,
        prestacion_it_directa=prestacion_directa,
        complemento_convenio_it=complemento_total,
        total_devengado_bruto=total,
        desglose_por_tramos=desglose,
    )
