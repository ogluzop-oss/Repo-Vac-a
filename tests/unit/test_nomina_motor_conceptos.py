"""
F4.3.3 · Motor de nómina — conceptos ampliados (puros, sin Qt/BD/PDF).

Devengos salariales (nocturnidad/bonus), no salariales con exención (transporte/dietas),
deducciones (anticipos/embargos), prorrateo de pagas extra y clasificación explícita.
"""

from src.rrhh.nomina_motor import (DEDUCCION, DEVENGO_NO_SALARIAL, DEVENGO_SALARIAL,
                                   NominaInput, calcular_nomina)
from src.rrhh.parametros_cotizacion import cargar_parametros

P = cargar_parametros(2025)   # exención transporte 100€/mes, dietas 300€/mes (cotizacion_es.json)


def _calc(**kw):
    return calcular_nomina(NominaInput(salario_base_mensual=2000, grupo_cotizacion="1", **kw), P)


def _dev(r, concepto):
    return next((d for d in r.devengos if d["concepto"] == concepto), None)


def _ded(r, concepto):
    return next((d for d in r.deducciones if d["concepto"] == concepto), None)


# 1. Plus transporte exento (≤ límite) → no tributa, no cotiza, pero se paga
def test_transporte_exento():
    r = _calc(plus_transporte=80, irpf_tipo=15)
    d = _dev(r, "Plus transporte")
    assert d["clase"] == DEVENGO_NO_SALARIAL and d["cotiza"] is False
    assert d["tributable"] == 0.0 and d["exenta"] == 80.0
    assert r.bccc == 2000.0                          # no entra en base de cotización
    assert r.base_irpf == 2000.0                     # no tributa
    assert r.total_devengado == 2080.0               # sí se paga


# 2. Dietas exentas (≤ límite)
def test_dietas_exentas():
    r = _calc(dietas=250)
    assert _dev(r, "Dietas")["tributable"] == 0.0
    assert r.base_irpf == 2000.0


# 3. Dietas parcialmente sujetas (exceso sobre 300 tributa)
def test_dietas_parcialmente_sujetas():
    r = _calc(dietas=400, irpf_tipo=10)
    d = _dev(r, "Dietas")
    assert d["exenta"] == 300.0 and d["tributable"] == 100.0
    assert r.base_irpf == 2100.0                      # 2000 + 100 no exento
    assert r.irpf_importe == 210.0                    # 2100 * 10%
    assert r.bccc == 2000.0                           # dietas no cotizan


# 4. Nocturnidad (salarial: cotiza + tributa)
def test_nocturnidad_salarial():
    r = _calc(nocturnidad=100)
    d = _dev(r, "Nocturnidad")
    assert d["clase"] == DEVENGO_SALARIAL and d["cotiza"] is True
    assert r.bccc == 2100.0                           # entra en base
    assert r.base_irpf == 2100.0


# 5. Bonus (salarial)
def test_bonus_salarial():
    r = _calc(bonus=200)
    assert _dev(r, "Bonus / incentivos")["clase"] == DEVENGO_SALARIAL
    assert r.bccc == 2200.0


# 6. Anticipos (deducción, no afecta bases/SS/IRPF)
def test_anticipos_deduccion():
    base = _calc()
    r = _calc(anticipos=150)
    assert _ded(r, "Anticipos")["importe"] == 150.0
    assert r.bccc == base.bccc and r.base_irpf == base.base_irpf
    assert r.ss_trabajador["total"] == base.ss_trabajador["total"]
    assert r.liquido == round(base.liquido - 150.0, 2)


# 7. Embargos (deducción)
def test_embargos_deduccion():
    base = _calc()
    r = _calc(embargos=75)
    assert _ded(r, "Embargos")["importe"] == 75.0
    assert r.liquido == round(base.liquido - 75.0, 2)


# 8. Prorrateo de pagas extra
def test_prorrateo_pagas_extra():
    p12 = _calc(num_pagas=12)
    p14 = _calc(num_pagas=14, pagas_extra_prorrateadas=True)
    # 14 pagas → prorrateo = 2000 * 2/12 = 333.33 entra en base y devengo
    assert p12.meta["prorrateo_extra"] == 0.0
    assert p14.meta["prorrateo_extra"] == 333.33
    assert p14.bccc == round(2000 + 333.33, 2)
    assert _dev(p14, "Prorrateo pagas extra")["importe"] == 333.33
    # No prorrateadas: base sí incluye prorrateo, devengo del mes NO
    p14np = _calc(num_pagas=14, pagas_extra_prorrateadas=False)
    assert p14np.bccc == round(2000 + 333.33, 2)       # cotización siempre prorratea
    assert _dev(p14np, "Prorrateo pagas extra") is None  # no se devenga este mes
    assert p14np.total_devengado == 2000.0


# 9. Combinación completa de conceptos
def test_combinacion_completa():
    r = _calc(plus_convenio=100, nocturnidad=50, bonus=30, horas_extra=40,
              plus_transporte=150, dietas=350, anticipos=20, embargos=10, irpf_tipo=15)
    # base cotización: 2000 + 100 + 50 + 30 (sin transporte/dietas/horas extra) = 2180
    assert r.bccc == 2180.0
    assert r.bccp == 2220.0                            # + horas extra
    # total devengado: salariales (2000+100+50+30+40=2220) + no salariales (150+350=500)
    assert r.total_devengado == 2720.0
    # base IRPF: salariales 2220 + transporte no exento 50 + dietas no exento 50 = 2320
    assert r.base_irpf == 2320.0
    # deducciones: SS + IRPF + 20 + 10
    assert _ded(r, "Anticipos")["importe"] == 20.0 and _ded(r, "Embargos")["importe"] == 10.0
    assert r.liquido == round(r.total_devengado - r.total_deducciones, 2)


# 10. Determinismo con todos los conceptos
def test_determinismo_completo():
    kw = dict(plus_convenio=33.33, nocturnidad=11.11, bonus=22.22, horas_extra=9.99,
              plus_transporte=120, dietas=333.33, anticipos=5.5, embargos=4.4,
              num_pagas=14, irpf_tipo=14)
    r1 = _calc(**kw); r2 = _calc(**kw)
    assert (r1.total_devengado, r1.bccc, r1.base_irpf, r1.total_deducciones, r1.liquido) == \
           (r2.total_devengado, r2.bccc, r2.base_irpf, r2.total_deducciones, r2.liquido)
