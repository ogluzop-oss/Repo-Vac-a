"""
F4.3.2 · Motor de nómina (función pura). Tests unitarios SIN Qt/BD/PDF/migraciones.

Verifica devengos, bases con topes por grupo, SS trabajador/empresa por contingencia,
IRPF tipo fijo, líquido, carga de parámetros JSON y determinismo.
"""

from src.rrhh.nomina_motor import (NominaInput, NominaResultado, ParametrosAnio,
                                   calcular_nomina)
from src.rrhh.parametros_cotizacion import cargar_parametros

P = cargar_parametros(2026)   # parámetros reales del recurso assets/rrhh/cotizacion_es.json


def _calc(**kw):
    return calcular_nomina(NominaInput(**kw), P)


# 1. Nómina simple (caso de referencia calculado a mano)
def test_nomina_simple():
    r = _calc(salario_base_mensual=2000, grupo_cotizacion="1", irpf_tipo=15)
    assert r.total_devengado == 2000.0
    assert r.bccc == 2000.0 and r.bccp == 2000.0
    assert r.ss_trabajador["comunes"] == 94.0      # 2000 * 4.70%
    assert r.ss_trabajador["desempleo"] == 31.0    # 2000 * 1.55% (indefinido)
    assert r.ss_trabajador["fp"] == 2.0            # 2000 * 0.10%
    assert r.ss_trabajador["mei"] == 2.6           # 2000 * 0.13%
    assert r.ss_trabajador["total"] == 129.6
    assert r.irpf_importe == 300.0                 # 2000 * 15%
    assert r.total_deducciones == 429.6
    assert r.liquido == 1570.4


# 2. Diferentes grupos de cotización (min distinto)
def test_grupos_distintos_min():
    bajo = _calc(salario_base_mensual=1000, grupo_cotizacion="1")   # min grupo 1 = 1847.40
    medio = _calc(salario_base_mensual=1000, grupo_cotizacion="7")  # min grupo 7 = 1323.00
    assert bajo.bccc == 1847.40
    assert medio.bccc == 1323.00


# 3. Tope máximo
def test_tope_maximo():
    r = _calc(salario_base_mensual=6000, grupo_cotizacion="1")
    assert r.bccc == 4909.50                       # acotado al tope máximo mensual


# 4. Tope mínimo
def test_tope_minimo():
    r = _calc(salario_base_mensual=900, grupo_cotizacion="7")
    assert r.bccc == 1323.00                       # acotado al mínimo del grupo/tope


# 5/6. Contrato indefinido vs temporal (cambia el % desempleo)
def test_contrato_indefinido_vs_temporal():
    ind = _calc(salario_base_mensual=2000, grupo_cotizacion="1", tipo_contrato="indefinido")
    tmp = _calc(salario_base_mensual=2000, grupo_cotizacion="1", tipo_contrato="temporal")
    assert ind.ss_trabajador["desempleo"] == 31.0   # 1.55%
    assert tmp.ss_trabajador["desempleo"] == 32.0   # 1.60%
    assert tmp.ss_trabajador["total"] != ind.ss_trabajador["total"]


# 7. SS trabajador (suma de contingencias)
def test_ss_trabajador_suma():
    r = _calc(salario_base_mensual=2000, grupo_cotizacion="1")
    suma = sum(v for k, v in r.ss_trabajador.items() if k != "total")
    assert round(suma, 2) == r.ss_trabajador["total"]


# 8. SS empresa (presente y coherente, no resta al líquido)
def test_ss_empresa_presente():
    r = _calc(salario_base_mensual=2000, grupo_cotizacion="1")
    assert r.ss_empresa["comunes"] == 472.0        # 2000 * 23.60%
    assert r.ss_empresa["at_ep"] == 30.0           # 2000 * 1.50%
    assert r.ss_empresa["total"] == 641.4
    # la SS empresa NO afecta al líquido
    assert r.liquido == round(r.total_devengado - r.total_deducciones, 2)


# 9. IRPF (tipo fijo; usa defecto si no se indica)
def test_irpf_tipo():
    r1 = _calc(salario_base_mensual=2000, grupo_cotizacion="1", irpf_tipo=20)
    assert r1.irpf_importe == 400.0
    r2 = _calc(salario_base_mensual=2000, grupo_cotizacion="1")   # sin tipo → defecto 15
    assert r2.irpf_tipo == 15.0 and r2.irpf_importe == 300.0


# 10. Líquido final con plus + horas extra
def test_liquido_con_plus_y_horas_extra():
    r = _calc(salario_base_mensual=2000, plus_convenio=100, horas_extra=50,
              grupo_cotizacion="1", irpf_tipo=15)
    assert r.total_devengado == 2150.0
    assert r.bccc == 2100.0                         # base + plus (sin horas extra)
    assert r.bccp == 2150.0                         # + horas extra
    assert r.liquido == round(2150.0 - r.total_deducciones, 2)


# 11. Carga correcta de parámetros JSON
def test_carga_parametros():
    assert isinstance(P, ParametrosAnio)
    assert P.anio == 2026 and P.pais == "ES"
    assert P.ss_trabajador["comunes"] == 4.70
    assert P.tope_max_mensual == 4909.50
    assert "1" in P.grupos


# 12. Determinismo + pureza (mismo input → mismo output; sin efectos colaterales)
def test_determinismo():
    e = NominaInput(salario_base_mensual=1850.55, plus_convenio=33.33, horas_extra=12.10,
                    grupo_cotizacion="3", tipo_contrato="temporal", irpf_tipo=14)
    r1 = calcular_nomina(e, P)
    r2 = calcular_nomina(e, P)
    assert isinstance(r1, NominaResultado)
    assert (r1.total_devengado, r1.bccc, r1.bccp, r1.ss_trabajador["total"],
            r1.irpf_importe, r1.liquido) == (
           r2.total_devengado, r2.bccc, r2.bccp, r2.ss_trabajador["total"],
           r2.irpf_importe, r2.liquido)


# Resolución de la ambigüedad mensual/anual
def test_desde_anual_no_recalcula_dos_veces():
    mensual = NominaInput(salario_base_mensual=2000, grupo_cotizacion="1")
    anual = NominaInput.desde_anual(28000, num_pagas=14, grupo_cotizacion="1")
    assert anual.salario_base_mensual == 2000.0    # 28000 / 14, una sola vez
    assert calcular_nomina(mensual, P).liquido == calcular_nomina(anual, P).liquido
