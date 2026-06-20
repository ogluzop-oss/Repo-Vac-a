"""
Motor de nómina — FUENTE ÚNICA de cálculo (F4.3.2 + F4.3.3).

Función PURA `calcular_nomina(entrada, parametros) -> NominaResultado`. Sin Qt, sin BD,
sin `self`, sin globales, sin configuración de usuario: depende SOLO de `NominaInput` y
`ParametrosAnio`. Determinista. Lo consumirán render y persistencia en F4.3.4 (hoy
queda aislado y testeado).

Decisión sobre la ambigüedad mensual/anual (auditoría F4.3.0): el motor trabaja SIEMPRE
con `salario_base_mensual` EXPLÍCITO (no divide nada por el nº de pagas). Para entradas
en salario anual, usar `NominaInput.desde_anual(salario_anual, num_pagas, ...)`.

Clasificación EXPLÍCITA de todo concepto (sin cálculos ad hoc):
  - DEVENGO_SALARIAL    → cotiza (BCCC) y tributa (IRPF): salario base, plus convenio,
                          nocturnidad, bonus, antigüedad, prorrateo pagas extra, horas
                          extra (cotiza en BCCP).
  - DEVENGO_NO_SALARIAL → no cotiza; tributa solo el exceso sobre la exención: plus
                          transporte, dietas.
  - DEDUCCION           → resta al líquido sin afectar bases/SS/IRPF: anticipos, embargos.

Pagas extra: la base de cotización SIEMPRE incluye el prorrateo de pagas extra
(`prorrateo = salario_base * max(num_pagas-12,0)/12`). El DEVENGO del mes incluye ese
prorrateo solo si las extras están prorrateadas en el pago (`pagas_extra_prorrateadas`).

IRPF: tipo fijo (hueco estructural `irpf_modo` para tablas en fase posterior).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("rrhh.nomina_motor")

# Clasificación de conceptos (explícita)
DEVENGO_SALARIAL = "DEVENGO_SALARIAL"
DEVENGO_NO_SALARIAL = "DEVENGO_NO_SALARIAL"
DEDUCCION = "DEDUCCION"


def _r(x) -> float:
    return round(float(x or 0), 2)


# ── Parámetros legales ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ParametrosAnio:
    anio: int
    pais: str
    ss_trabajador: dict
    ss_empresa: dict
    desempleo_trabajador: dict
    desempleo_empresa: dict
    tope_max_mensual: float
    tope_min_mensual: float
    grupos: dict
    irpf_modo: str = "tipo_fijo"
    irpf_tipo_defecto: float = 15.0
    exencion_transporte_mensual: float = 0.0
    exencion_dietas_mensual: float = 0.0

    @classmethod
    def desde_dict(cls, anio: int, pais: str, d: dict) -> "ParametrosAnio":
        bases = d.get("bases", {})
        irpf = d.get("irpf", {})
        ex = d.get("exenciones", {})
        return cls(
            anio=anio, pais=pais,
            ss_trabajador=dict(d.get("ss_trabajador", {})),
            ss_empresa=dict(d.get("ss_empresa", {})),
            desempleo_trabajador=dict(d.get("desempleo_trabajador", {})),
            desempleo_empresa=dict(d.get("desempleo_empresa", {})),
            tope_max_mensual=float(bases.get("tope_max_mensual", 0) or 0),
            tope_min_mensual=float(bases.get("tope_min_mensual", 0) or 0),
            grupos={str(k): dict(v) for k, v in (d.get("grupos") or {}).items()},
            irpf_modo=irpf.get("modo", "tipo_fijo"),
            irpf_tipo_defecto=float(irpf.get("tipo_defecto", 15.0) or 15.0),
            exencion_transporte_mensual=float(ex.get("transporte_mensual", 0) or 0),
            exencion_dietas_mensual=float(ex.get("dietas_mensual", 0) or 0),
        )

    def limites_grupo(self, grupo) -> tuple[float, float]:
        g = self.grupos.get(str(grupo))
        if g is None:                       # incidencia: grupo no parametrizado → topes globales
            logger.warning("Grupo de cotización '%s' no parametrizado (%s); se usan topes globales.",
                           grupo, self.anio)
            g = {}
        gmin = float(g.get("min", self.tope_min_mensual) or self.tope_min_mensual)
        gmax = float(g.get("max", self.tope_max_mensual) or self.tope_max_mensual)
        low = max(gmin, self.tope_min_mensual) if self.tope_min_mensual else gmin
        high = min(gmax, self.tope_max_mensual) if self.tope_max_mensual else gmax
        return low, high


# ── Entrada ───────────────────────────────────────────────────────────────────
@dataclass
class NominaInput:
    salario_base_mensual: float
    num_pagas: int = 12
    grupo_cotizacion: str = "7"
    tipo_contrato: str = "indefinido"
    irpf_tipo: float | None = None
    pagas_extra_prorrateadas: bool = True
    # Devengos salariales (cotizan y tributan)
    plus_convenio: float = 0.0
    nocturnidad: float = 0.0
    bonus: float = 0.0
    antiguedad: float = 0.0          # importe (no alimentado aún por el formulario)
    horas_extra: float = 0.0
    # Devengos no salariales (no cotizan; tributa el exceso sobre exención)
    plus_transporte: float = 0.0
    dietas: float = 0.0
    # Deducciones (restan al líquido; no afectan bases/SS/IRPF)
    anticipos: float = 0.0
    embargos: float = 0.0

    @classmethod
    def desde_anual(cls, salario_anual, num_pagas=12, **kw) -> "NominaInput":
        np = int(num_pagas or 12) or 12
        mensual = _r(float(salario_anual or 0) / np)
        return cls(salario_base_mensual=mensual, num_pagas=np, **kw)


# ── Resultado ─────────────────────────────────────────────────────────────────
@dataclass
class NominaResultado:
    devengos: list = field(default_factory=list)       # [{concepto, importe, clase, cotiza, tributable}]
    deducciones: list = field(default_factory=list)     # [{concepto, importe, clase}]
    total_devengado: float = 0.0
    total_deducciones: float = 0.0
    bccc: float = 0.0
    bccp: float = 0.0
    base_at_ep: float = 0.0
    ss_trabajador: dict = field(default_factory=dict)
    ss_empresa: dict = field(default_factory=dict)
    base_irpf: float = 0.0
    irpf_tipo: float = 0.0
    irpf_importe: float = 0.0
    liquido: float = 0.0
    meta: dict = field(default_factory=dict)


# ── Cálculo (orden fijo: devengos → bases → SS → IRPF → deducciones → líquido) ──
def calcular_nomina(entrada: NominaInput, parametros: ParametrosAnio) -> NominaResultado:
    p = parametros
    e = entrada
    sal = _r(e.salario_base_mensual)

    # Prorrateo de pagas extra (la cotización SIEMPRE lo incluye)
    prorrateo = _r(sal * max(int(e.num_pagas or 12) - 12, 0) / 12)

    # 1) DEVENGOS — clasificados explícitamente
    devengos = []

    def _dev_sal(concepto, importe, cotiza=True):
        if importe:
            devengos.append({"concepto": concepto, "importe": _r(importe),
                             "clase": DEVENGO_SALARIAL, "cotiza": cotiza,
                             "tributable": _r(importe)})

    _dev_sal("Salario base", sal)
    _dev_sal("Plus convenio", e.plus_convenio)
    _dev_sal("Antigüedad", e.antiguedad)
    _dev_sal("Nocturnidad", e.nocturnidad)
    _dev_sal("Bonus / incentivos", e.bonus)
    if e.pagas_extra_prorrateadas and prorrateo:
        _dev_sal("Prorrateo pagas extra", prorrateo)
    _dev_sal("Horas extra", e.horas_extra)   # cotiza en BCCP (tratada aparte abajo)

    # No salariales: exención parametrizada (exenta no tributa; exceso tributa)
    def _dev_no_sal(concepto, importe, exencion):
        importe = _r(importe)
        if not importe:
            return 0.0
        exenta = _r(min(importe, max(exencion, 0)))
        no_exenta = _r(importe - exenta)
        devengos.append({"concepto": concepto, "importe": importe,
                         "clase": DEVENGO_NO_SALARIAL, "cotiza": False,
                         "tributable": no_exenta, "exenta": exenta})
        return no_exenta

    transp_no_exenta = _dev_no_sal("Plus transporte", e.plus_transporte,
                                   p.exencion_transporte_mensual)
    dietas_no_exenta = _dev_no_sal("Dietas", e.dietas, p.exencion_dietas_mensual)

    total_devengado = _r(sum(d["importe"] for d in devengos))

    # 2) BASES — la cotización incluye complementos salariales + prorrateo (no horas extra)
    low, high = p.limites_grupo(e.grupo_cotizacion)
    base_cot = _r(sal + _r(e.plus_convenio) + _r(e.antiguedad) + _r(e.nocturnidad)
                  + _r(e.bonus) + prorrateo)
    bccc = _r(min(max(base_cot, low), high))
    he = _r(e.horas_extra)
    bccp = _r(bccc + he)
    base_at_ep = bccp

    # 3) SS TRABAJADOR
    tc = e.tipo_contrato if e.tipo_contrato in ("indefinido", "temporal") else "indefinido"
    st = p.ss_trabajador
    ss_t = {
        "comunes": _r(bccc * st.get("comunes", 0) / 100),
        "desempleo": _r(bccp * p.desempleo_trabajador.get(tc, 0) / 100),
        "fp": _r(bccp * st.get("fp", 0) / 100),
        "mei": _r(bccc * st.get("mei", 0) / 100),
        "horas_extra": _r(he * st.get("horas_extra", 0) / 100),
    }
    ss_t["total"] = _r(sum(v for k, v in ss_t.items() if k != "total"))

    # 4) SS EMPRESA (informativo)
    se = p.ss_empresa
    ss_e = {
        "comunes": _r(bccc * se.get("comunes", 0) / 100),
        "desempleo": _r(bccp * p.desempleo_empresa.get(tc, 0) / 100),
        "fp": _r(bccp * se.get("fp", 0) / 100),
        "fogasa": _r(bccp * se.get("fogasa", 0) / 100),
        "at_ep": _r(base_at_ep * se.get("at_ep", 0) / 100),
        "mei": _r(bccc * se.get("mei", 0) / 100),
        "horas_extra": _r(he * se.get("horas_extra", 0) / 100),
    }
    ss_e["total"] = _r(sum(v for k, v in ss_e.items() if k != "total"))

    # 5) IRPF — base = devengos salariales íntegros + exceso no exento de no salariales
    base_irpf = _r(sum(d["tributable"] for d in devengos))
    irpf_tipo = e.irpf_tipo if e.irpf_tipo is not None else p.irpf_tipo_defecto
    irpf_importe = _r(base_irpf * float(irpf_tipo) / 100)

    # 6) DEDUCCIONES (anticipos/embargos no afectan bases/SS/IRPF) + 7) LÍQUIDO
    deducciones = [
        {"concepto": "Cuota S.S. trabajador", "importe": ss_t["total"], "clase": DEDUCCION},
        {"concepto": "Retención IRPF", "importe": irpf_importe, "clase": DEDUCCION},
    ]
    if e.anticipos:
        deducciones.append({"concepto": "Anticipos", "importe": _r(e.anticipos), "clase": DEDUCCION})
    if e.embargos:
        deducciones.append({"concepto": "Embargos", "importe": _r(e.embargos), "clase": DEDUCCION})
    total_deducciones = _r(sum(d["importe"] for d in deducciones))
    liquido = _r(total_devengado - total_deducciones)

    return NominaResultado(
        devengos=devengos, deducciones=deducciones,
        total_devengado=total_devengado, total_deducciones=total_deducciones,
        bccc=bccc, bccp=bccp, base_at_ep=base_at_ep,
        ss_trabajador=ss_t, ss_empresa=ss_e,
        base_irpf=base_irpf, irpf_tipo=_r(irpf_tipo), irpf_importe=irpf_importe,
        liquido=liquido,
        meta={"anio": p.anio, "pais": p.pais, "grupo": str(e.grupo_cotizacion),
              "tipo_contrato": tc, "prorrateo_extra": prorrateo,
              "transporte_no_exento": transp_no_exenta, "dietas_no_exento": dietas_no_exenta},
    )
