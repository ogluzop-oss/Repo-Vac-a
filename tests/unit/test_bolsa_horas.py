"""Tests unitarios del motor PURO de bolsa de horas (`src.rrhh.bolsa_horas.calcular_bolsa_horas`,
RRHH Fase E). Sin BD/Qt — cubre exactamente los casos pedidos: día ordinario exacto (sin saldo),
festivo (excluido de esperadas/compensar), baja (déficit de día completo), ordinario corto
(déficit) y ordinario largo (exceso)."""

import datetime as dt

import pytest

from src.rrhh.bolsa_horas import calcular_bolsa_horas


def _semana(lunes: dt.date):
    return [lunes + dt.timedelta(days=i) for i in range(7)]


def test_semana_normal_sin_desviacion_no_genera_saldo():
    lunes = dt.date(2026, 1, 5)
    dias = _semana(lunes)
    fichajes = {d: 8.0 for d in dias}  # exactamente horas_diarias cada día
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=lunes, fecha_fin=lunes + dt.timedelta(days=6),
        horas_diarias=8.0, dias_festivos=[], dias_baja=[], fichajes_por_dia=fichajes,
    )
    assert r["horas_esperadas"] == pytest.approx(56.0)
    assert r["horas_trabajadas"] == pytest.approx(56.0)
    assert r["horas_compensar_empleado"] == 0.0
    assert r["horas_compensar_empresa"] == 0.0
    assert r["dias_ordinarios"] == 7
    assert r["dias_festivos"] == 0
    assert r["dias_baja"] == 0


def test_dia_festivo_excluido_de_esperadas_y_compensar():
    lunes = dt.date(2026, 1, 5)
    martes = lunes + dt.timedelta(days=1)
    # Semana de un solo día: el martes, marcado festivo, sin fichaje.
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=martes, fecha_fin=martes,
        horas_diarias=8.0, dias_festivos=[martes], dias_baja=[], fichajes_por_dia={},
    )
    assert r["horas_esperadas"] == 0.0
    assert r["horas_trabajadas"] == 0.0
    assert r["horas_compensar_empleado"] == 0.0
    assert r["horas_compensar_empresa"] == 0.0
    assert r["dias_festivos"] == 1
    assert r["dias_ordinarios"] == 0


def test_dia_baja_cuenta_como_deficit_de_jornada_completa():
    lunes = dt.date(2026, 1, 5)
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=lunes, fecha_fin=lunes,
        horas_diarias=8.0, dias_festivos=[], dias_baja=[lunes], fichajes_por_dia={},
    )
    assert r["horas_esperadas"] == 8.0
    assert r["horas_trabajadas"] == 0.0
    assert r["horas_compensar_empleado"] == 8.0
    assert r["horas_compensar_empresa"] == 0.0
    assert r["dias_baja"] == 1


def test_dia_ordinario_trabajado_de_menos_genera_deficit():
    lunes = dt.date(2026, 1, 5)
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=lunes, fecha_fin=lunes,
        horas_diarias=8.0, dias_festivos=[], dias_baja=[], fichajes_por_dia={lunes: 5.5},
    )
    assert r["horas_esperadas"] == 8.0
    assert r["horas_trabajadas"] == 5.5
    assert r["horas_compensar_empleado"] == pytest.approx(2.5)
    assert r["horas_compensar_empresa"] == 0.0


def test_dia_ordinario_trabajado_de_mas_genera_exceso():
    lunes = dt.date(2026, 1, 5)
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=lunes, fecha_fin=lunes,
        horas_diarias=8.0, dias_festivos=[], dias_baja=[], fichajes_por_dia={lunes: 10.0},
    )
    assert r["horas_esperadas"] == 8.0
    assert r["horas_trabajadas"] == 10.0
    assert r["horas_compensar_empleado"] == 0.0
    assert r["horas_compensar_empresa"] == pytest.approx(2.0)


def test_mezcla_festivo_baja_ordinario_corto_y_largo():
    lunes = dt.date(2026, 1, 5)          # ordinario, corto (6h de 8h)
    martes = lunes + dt.timedelta(days=1)   # festivo
    miercoles = lunes + dt.timedelta(days=2)  # baja
    jueves = lunes + dt.timedelta(days=3)   # ordinario, largo (9h de 8h)
    r = calcular_bolsa_horas(
        id_empleado=1, fecha_inicio=lunes, fecha_fin=jueves,
        horas_diarias=8.0, dias_festivos=[martes], dias_baja=[miercoles],
        fichajes_por_dia={lunes: 6.0, jueves: 9.0},
    )
    # esperadas: lunes(8) + martes(0, festivo) + miércoles(8, baja) + jueves(8) = 24
    assert r["horas_esperadas"] == 24.0
    assert r["horas_trabajadas"] == pytest.approx(15.0)  # 6 + 9 (miércoles no fichó)
    # compensar empleado: lunes déficit 2h + miércoles déficit completo 8h = 10h
    assert r["horas_compensar_empleado"] == pytest.approx(10.0)
    # compensar empresa: jueves exceso 1h
    assert r["horas_compensar_empresa"] == pytest.approx(1.0)
    assert r["dias_festivos"] == 1
    assert r["dias_baja"] == 1
    assert r["dias_ordinarios"] == 2


def test_fecha_inicio_posterior_a_fin_lanza_error():
    lunes = dt.date(2026, 1, 5)
    with pytest.raises(ValueError):
        calcular_bolsa_horas(
            id_empleado=1, fecha_inicio=lunes, fecha_fin=lunes - dt.timedelta(days=1),
            horas_diarias=8.0, dias_festivos=[], dias_baja=[], fichajes_por_dia={},
        )
