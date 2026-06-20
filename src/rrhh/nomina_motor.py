"""
Motor de nómina — FUENTE ÚNICA de cálculo (F4.3.2).

Función PURA `calcular_nomina(entrada, parametros) -> NominaResultado`. Sin Qt, sin BD,
sin `self`, sin globales, sin configuración de usuario: depende SOLO de `NominaInput` y
`ParametrosAnio`. Determinista. Lo consumirán render y persistencia en F4.3.4 (hoy
queda aislado y testeado).

Decisión sobre la ambigüedad mensual/anual (auditoría F4.3.0): el motor trabaja SIEMPRE
con `salario_base_mensual` EXPLÍCITO (no divide nada por el nº de pagas). Para entradas
en salario anual, usar `NominaInput.desde_anual(salario_anual, num_pagas, ...)`, que
hace la división una sola vez y de forma documentada.

Alcance F4.3.2 (devengos: salario base + plus convenio + horas extra; SS por
contingencias trabajador/empresa; bases con topes por grupo; IRPF tipo fijo). Dietas,
nocturnidad, bonus, anticipos y embargos se integran en F4.3.3 (ya hay hueco estructural).
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _r(x) -> float:
    return round(float(x or 0), 2)


# ── Parámetros legales ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ParametrosAnio:
    anio: int
    pais: str
    ss_trabajador: dict          # {comunes, fp, mei, horas_extra}
    ss_empresa: dict             # {comunes, fp, fogasa, at_ep, mei, horas_extra}
    desempleo_trabajador: dict   # {indefinido, temporal}
    desempleo_empresa: dict      # {indefinido, temporal}
    tope_max_mensual: float
    tope_min_mensual: float
    grupos: dict                 # {"1": {"min","max"}, ...}
    irpf_modo: str = "tipo_fijo"
    irpf_tipo_defecto: float = 15.0

    @classmethod
    def desde_dict(cls, anio: int, pais: str, d: dict) -> "ParametrosAnio":
        bases = d.get("bases", {})
        irpf = d.get("irpf", {})
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
        )

    def limites_grupo(self, grupo) -> tuple[float, float]:
        """(base_min, base_max) para el grupo, acotados por los topes globales."""
        g = self.grupos.get(str(grupo)) or {}
        gmin = float(g.get("min", self.tope_min_mensual) or self.tope_min_mensual)
        gmax = float(g.get("max", self.tope_max_mensual) or self.tope_max_mensual)
        low = max(gmin, self.tope_min_mensual) if self.tope_min_mensual else gmin
        high = min(gmax, self.tope_max_mensual) if self.tope_max_mensual else gmax
        return low, high


# ── Entrada ───────────────────────────────────────────────────────────────────
@dataclass
class NominaInput:
    salario_base_mensual: float          # base mensual EXPLÍCITA (no se divide)
    num_pagas: int = 12                  # informativo en F4.3.2 (prorrateo en F4.3.3)
    grupo_cotizacion: str = "7"
    tipo_contrato: str = "indefinido"    # indefinido | temporal (rige el % desempleo)
    plus_convenio: float = 0.0
    horas_extra: float = 0.0             # importe en € de horas extra
    irpf_tipo: float | None = None       # % manual; si None → irpf_tipo_defecto del año

    @classmethod
    def desde_anual(cls, salario_anual, num_pagas=12, **kw) -> "NominaInput":
        np = int(num_pagas or 12) or 12
        mensual = _r(float(salario_anual or 0) / np)
        return cls(salario_base_mensual=mensual, num_pagas=np, **kw)


# ── Resultado ─────────────────────────────────────────────────────────────────
@dataclass
class NominaResultado:
    devengos: list = field(default_factory=list)      # [(concepto, importe)]
    total_devengado: float = 0.0
    bccc: float = 0.0
    bccp: float = 0.0
    base_at_ep: float = 0.0
    ss_trabajador: dict = field(default_factory=dict)  # por contingencia + 'total'
    ss_empresa: dict = field(default_factory=dict)
    base_irpf: float = 0.0
    irpf_tipo: float = 0.0
    irpf_importe: float = 0.0
    total_deducciones: float = 0.0
    liquido: float = 0.0
    meta: dict = field(default_factory=dict)


# ── Cálculo (orden fijo: devengos → bases → SS → IRPF → deducciones → líquido) ──
def calcular_nomina(entrada: NominaInput, parametros: ParametrosAnio) -> NominaResultado:
    p = parametros
    base_m = _r(entrada.salario_base_mensual)
    plus = _r(entrada.plus_convenio)
    he = _r(entrada.horas_extra)

    # 1) DEVENGOS
    devengos = [("Salario base", base_m)]
    if plus:
        devengos.append(("Plus convenio", plus))
    if he:
        devengos.append(("Horas extra", he))
    total_devengado = _r(base_m + plus + he)

    # 2) BASES (remuneración salarial mensual, acotada por topes del grupo)
    low, high = p.limites_grupo(entrada.grupo_cotizacion)
    remuneracion = _r(base_m + plus)               # sin horas extra
    bccc = _r(min(max(remuneracion, low), high))
    bccp = _r(bccc + he)                            # CP incluye horas extra
    base_at_ep = bccp

    # 3) SS TRABAJADOR (por contingencia)
    tc = entrada.tipo_contrato if entrada.tipo_contrato in ("indefinido", "temporal") else "indefinido"
    st = p.ss_trabajador
    ss_t = {
        "comunes": _r(bccc * st.get("comunes", 0) / 100),
        "desempleo": _r(bccp * p.desempleo_trabajador.get(tc, 0) / 100),
        "fp": _r(bccp * st.get("fp", 0) / 100),
        "mei": _r(bccc * st.get("mei", 0) / 100),
        "horas_extra": _r(he * st.get("horas_extra", 0) / 100),
    }
    ss_t["total"] = _r(sum(v for k, v in ss_t.items() if k != "total"))

    # 4) SS EMPRESA (por contingencia) — informativo (no resta al líquido)
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

    # 5) IRPF (tipo fijo en F4.3.2; base = devengos íntegros)
    irpf_tipo = entrada.irpf_tipo if entrada.irpf_tipo is not None else p.irpf_tipo_defecto
    base_irpf = total_devengado
    irpf_importe = _r(base_irpf * float(irpf_tipo) / 100)

    # 6) DEDUCCIONES + 7) LÍQUIDO
    total_deducciones = _r(ss_t["total"] + irpf_importe)
    liquido = _r(total_devengado - total_deducciones)

    return NominaResultado(
        devengos=devengos, total_devengado=total_devengado,
        bccc=bccc, bccp=bccp, base_at_ep=base_at_ep,
        ss_trabajador=ss_t, ss_empresa=ss_e,
        base_irpf=base_irpf, irpf_tipo=_r(irpf_tipo), irpf_importe=irpf_importe,
        total_deducciones=total_deducciones, liquido=liquido,
        meta={"anio": p.anio, "pais": p.pais, "grupo": str(entrada.grupo_cotizacion),
              "tipo_contrato": tc},
    )
