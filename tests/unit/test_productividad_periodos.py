"""
Fase Productividad · `periodos.limites_periodo`/`navegar` — cálculo calendario puro, sin BD.
"""

import datetime as _dt

from src.services.productividad import periodos as P


def test_diario_es_el_mismo_dia():
    d = _dt.date(2026, 3, 11)
    assert P.limites_periodo("diario", d) == (d, d)


def test_semanal_lunes_a_domingo():
    # 2026-03-11 es miércoles → semana 09-15 de marzo (lunes a domingo)
    d = _dt.date(2026, 3, 11)
    desde, hasta = P.limites_periodo("semanal", d)
    assert desde == _dt.date(2026, 3, 9) and hasta == _dt.date(2026, 3, 15)
    assert desde.weekday() == 0 and hasta.weekday() == 6


def test_mensual_primer_y_ultimo_dia():
    desde, hasta = P.limites_periodo("mensual", _dt.date(2026, 2, 10))
    assert desde == _dt.date(2026, 2, 1) and hasta == _dt.date(2026, 2, 28)


def test_bimestral_pares_de_meses():
    desde, hasta = P.limites_periodo("bimestral", _dt.date(2026, 4, 15))
    assert desde == _dt.date(2026, 3, 1) and hasta == _dt.date(2026, 4, 30)


def test_trimestral_calendario():
    desde, hasta = P.limites_periodo("trimestral", _dt.date(2026, 8, 1))
    assert desde == _dt.date(2026, 7, 1) and hasta == _dt.date(2026, 9, 30)


def test_semestral_dos_mitades():
    d1 = P.limites_periodo("semestral", _dt.date(2026, 1, 15))
    d2 = P.limites_periodo("semestral", _dt.date(2026, 9, 15))
    assert d1 == (_dt.date(2026, 1, 1), _dt.date(2026, 6, 30))
    assert d2 == (_dt.date(2026, 7, 1), _dt.date(2026, 12, 31))


def test_anual_natural():
    desde, hasta = P.limites_periodo("anual", _dt.date(2026, 6, 1))
    assert desde == _dt.date(2026, 1, 1) and hasta == _dt.date(2026, 12, 31)


def test_bimensual_catorce_dias_alineados_a_semana_iso():
    desde, hasta = P.limites_periodo("bimensual", _dt.date(2026, 3, 11))
    assert (hasta - desde).days == 13
    assert desde.weekday() == 0  # empieza en lunes


def test_obligatorios_son_exactamente_tres():
    assert set(P.OBLIGATORIOS) == {"mensual", "semestral", "anual"}


def test_tipo_desconocido_lanza_valueerror():
    import pytest
    with pytest.raises(ValueError):
        P.limites_periodo("quincenal", _dt.date.today())


def test_navegar_atras_dentro_del_anio_en_curso():
    hoy = _dt.date.today()
    anterior = P.navegar("mensual", hoy, "atras")
    if hoy.month > 1:
        assert anterior is not None and anterior.year == hoy.year
    # Si estamos en enero, retroceder un mes cruzaría al año anterior → bloqueado.
    else:
        assert anterior is None


def test_navegar_adelante_nunca_al_futuro():
    hoy = _dt.date.today()
    siguiente = P.navegar("diario", hoy, "adelante")
    assert siguiente is None


def test_navegar_atras_bloqueado_antes_del_1_de_enero_del_anio_en_curso():
    primero_enero = _dt.date(_dt.date.today().year, 1, 1)
    assert P.navegar("diario", primero_enero, "atras") is None
