"""Tests unitarios del comprobador PURO de descansos mínimos legales (`src.rrhh.descansos`,
RRHH Fase E, punto 4). Sin BD/Qt — cubre exactamente los casos pedidos: semana normal sin
violaciones, hueco <12h entre turnos (violación diaria) y descanso semanal (1,5 días) válido vs
violado."""

from src.rrhh.descansos import verificar_descansos_semana


def _turno(h_ini, m_ini, h_fin, m_fin):
    return {"ini_min": h_ini * 60 + m_ini, "fin_min": h_fin * 60 + m_fin}


def test_semana_normal_lunes_a_viernes_sin_violaciones():
    # Lunes(0)..Viernes(4) 09:00-17:00, sábado/domingo libres.
    turnos = [_turno(9, 0, 17, 0) for _ in range(5)] + [None, None]
    violaciones = verificar_descansos_semana(turnos)
    assert violaciones == []


def test_menos_de_12h_de_descanso_entre_turnos_consecutivos_se_marca():
    # Lunes termina tarde (21:00), martes empieza pronto (08:00) -> 11h de descanso.
    turnos = [None] * 7
    turnos[0] = _turno(9, 0, 21, 0)
    turnos[1] = _turno(8, 0, 16, 0)
    violaciones = verificar_descansos_semana(turnos)
    diarias = [v for v in violaciones if v["tipo"] == "diario"]
    assert len(diarias) == 1
    v = diarias[0]
    assert v["dia_a"] == 0 and v["dia_b"] == 1
    assert v["horas_descanso"] == 11.0
    assert "lunes" in v["mensaje"] and "martes" in v["mensaje"]


def test_descanso_diario_de_exactamente_12h_no_viola():
    turnos = [None] * 7
    turnos[0] = _turno(8, 0, 16, 0)
    turnos[1] = _turno(4, 0, 12, 0)  # 12h exactas de descanso
    violaciones = verificar_descansos_semana(turnos)
    assert [v for v in violaciones if v["tipo"] == "diario"] == []


def test_descanso_semanal_valido_con_dos_dias_libres():
    # Trabaja lunes-viernes, sábado y domingo completamente libres -> > 36h de descanso.
    turnos = [_turno(9, 0, 17, 0) for _ in range(5)] + [None, None]
    violaciones = verificar_descansos_semana(turnos)
    assert [v for v in violaciones if v["tipo"] == "semanal"] == []


def test_descanso_semanal_violado_trabajando_los_7_dias():
    turnos = [_turno(9, 0, 17, 0) for _ in range(7)]
    violaciones = verificar_descansos_semana(turnos)
    semanales = [v for v in violaciones if v["tipo"] == "semanal"]
    assert len(semanales) == 1
    assert semanales[0]["horas_descanso"] < 36.0


def test_sin_turnos_no_genera_violaciones():
    assert verificar_descansos_semana([None] * 7) == []
