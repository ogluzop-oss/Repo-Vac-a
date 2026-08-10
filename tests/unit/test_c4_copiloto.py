"""
Tests Etapa C · Fase C4: Copiloto Empresarial (Área 8).

Verifica que el copiloto responde preguntas de negocio REUTILIZANDO el Centro/Panel/ia.consultas,
enruta por intención, respeta RBAC, SIEMPRE con datos verificables (nunca inventa) y no modifica datos.
"""

import inspect

import pytest

EMP = "T-COP-A"
GER = {"id": "g", "perfil": "GERENTE"}


@pytest.fixture()
def datos(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.services import inteligencia
    inteligencia.proponer("compras", "recomendacion", "Reponer A", "bajo", entidad="articulo",
                          entidad_ref="A", prioridad="ALTA", id_empresa=EMP)
    inteligencia.proponer("tesoreria", "riesgo", "Impago", "3 facturas", prioridad="ALTA",
                          id_empresa=EMP)
    inteligencia.proponer("inventario", "anomalia", "Rotura", "8 art", prioridad="MEDIA",
                          id_empresa=EMP)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_intent_situacion(datos):
    from src.services.inteligencia import copiloto
    r = copiloto.preguntar("¿Qué está ocurriendo?", id_empresa=EMP, usuario=GER)
    assert r["intent"] == "situacion" and r["verificable"] and r["fuente"] == "panel+centro"
    assert r["datos"]["resumen"]["total"] == 3


def test_intent_acciones(datos):
    from src.services.inteligencia import copiloto
    r = copiloto.preguntar("¿Qué debería hacer?", id_empresa=EMP, usuario=GER)
    assert r["intent"] == "acciones" and r["verificable"]
    assert len(r["datos"]) == 2                       # las 2 ALTA
    assert all(d["prioridad"] == "ALTA" for d in r["datos"])


def test_intent_riesgos(datos):
    from src.services.inteligencia import copiloto
    r = copiloto.preguntar("¿Qué riesgos existen?", id_empresa=EMP, usuario=GER)
    assert r["intent"] == "riesgos" and r["verificable"]
    assert {d["tipo"] for d in r["datos"]} == {"riesgo", "anomalia"}


def test_rbac_y_nunca_inventa(datos):
    from src.services.inteligencia import copiloto
    # Sin permiso → no autorizado.
    assert copiloto.preguntar("¿Qué ocurre?", id_empresa=EMP,
                              usuario={"id": "x", "perfil": "SIN"})["intent"] == "no_autorizado"
    # Pregunta libre sin datos → responde que no es verificable (no inventa).
    r = copiloto.preguntar("cuéntame un chiste sobre el clima", id_empresa=EMP, usuario=GER)
    assert r["intent"] in ("no_verificable", "desconocido") and r["verificable"] is False


def test_reutiliza_no_motor_nuevo():
    from src.services.inteligencia import copiloto
    src = inspect.getsource(copiloto)
    assert "ia.consultas" in src or "from src.services.ia import consultas" in src
    assert "inteligencia" in src and "panel" in src
    for prohibido in ("INSERT INTO", "UPDATE ", "CREATE TABLE"):
        assert prohibido not in src
    d = copiloto.descriptor()
    assert d["inventa"] is False and d["modifica_datos"] is False and d["motor_nuevo"] is False
