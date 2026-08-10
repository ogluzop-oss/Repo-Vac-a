"""
Tests Etapa C · Fase C5: Observabilidad avanzada (Área 9) + Aprendizaje supervisado (Área 10).

Verifica que se registran/reconstruyen las decisiones (métricas + replay) y que el aprendizaje deriva
un ranking de utilidad del feedback humano y reordena las recomendaciones, todo sobre el ledger
existente, solo lectura, sin reentrenar ni modificar datos.
"""

import inspect

import pytest

EMP = "T-OBS-A"
GER = {"id": "g", "perfil": "GERENTE"}


@pytest.fixture()
def historia(db):
    """Siembra un histórico con aceptadas/rechazadas/feedback para dos orígenes."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.services import inteligencia
    ids = []
    # origen 'buena.*': 2 aceptadas + feedback útil → alta utilidad
    for i in range(2):
        did = inteligencia.proponer("compras", "recomendacion", f"Buena {i}", "x",
                                    entidad_ref=f"B{i}", origen="buena.fuente", id_empresa=EMP)
        inteligencia.feedback(did, util=True, usuario=GER, id_empresa=EMP)
        inteligencia.aceptar(did, usuario=GER, id_empresa=EMP)
        ids.append(did)
    # origen 'mala.*': 2 rechazadas → baja utilidad
    for i in range(2):
        did = inteligencia.proponer("compras", "recomendacion", f"Mala {i}", "x",
                                    entidad_ref=f"M{i}", origen="mala.fuente", id_empresa=EMP)
        inteligencia.rechazar(did, motivo="no aplica", usuario=GER, id_empresa=EMP)
    yield ids
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_metricas(historia):
    from src.services.inteligencia import observabilidad
    m = observabilidad.metricas(EMP, usuario=GER)
    assert m["por_estado"].get("aceptada") == 2 and m["por_estado"].get("rechazada") == 2
    assert m["tasa_aceptacion"] == 0.5           # 2 aceptadas / 4 resueltas
    assert m["con_feedback"] == 4                 # 2 feedback útil + 2 motivos de rechazo


def test_replay_reconstruible(historia):
    from src.services.inteligencia import observabilidad
    r = observabilidad.replay(historia[0], id_empresa=EMP, usuario=GER)
    assert r and r["reconstruible"] and r["decision"]["estado"] == "aceptada"
    assert r["correlation_id"]                    # trazable en el Event Bus


def test_ranking_supervisado(historia):
    from src.services.inteligencia import aprendizaje
    rk = aprendizaje.ranking(EMP, por="origen", usuario=GER)
    assert rk["buena.fuente"]["utilidad"] > rk["mala.fuente"]["utilidad"]
    assert rk["mala.fuente"]["utilidad"] == 0.0   # 2 rechazadas → utilidad nula
    assert rk["buena.fuente"]["aceptadas"] == 2


def test_priorizar_aplica_aprendizaje(historia):
    from src.services.inteligencia import aprendizaje
    # Dos decisiones misma prioridad; la del origen mejor valorado va primero.
    decs = [{"titulo": "de mala", "prioridad": "MEDIA", "origen": "mala.fuente"},
            {"titulo": "de buena", "prioridad": "MEDIA", "origen": "buena.fuente"}]
    ordenadas = aprendizaje.priorizar(decs, EMP, por="origen", usuario=GER)
    assert ordenadas[0]["origen"] == "buena.fuente"   # aprendizaje reordena por utilidad histórica


def test_solo_lectura_supervisado():
    from src.services.inteligencia import aprendizaje, observabilidad
    for mod in (observabilidad, aprendizaje):
        src = inspect.getsource(mod)
        for prohibido in ("INSERT INTO", "UPDATE ", "CREATE TABLE", "DELETE FROM"):
            assert prohibido not in src
    assert aprendizaje.descriptor()["supervisado"] is True
    assert aprendizaje.descriptor()["reentrena_auto"] is False
    assert observabilidad.descriptor()["motor_nuevo"] is False
