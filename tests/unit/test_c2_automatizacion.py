"""
Tests Etapa C · Fase C2: Automatización Empresarial (puente transversal).

Verifica que las automatizaciones REUTILIZAN el Centro de Decisiones y Event Bus/Scheduler/Workflow
(no crean un segundo motor), reaccionan a disparadores/eventos generando SOLO propuestas (nunca
ejecutan cambios de negocio), deduplican, y son auditables.
"""

import inspect

import pytest

EMP = "T-AUT2-A"
GER = {"id": "g", "perfil": "GERENTE"}


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_regla_stock_bajo_propone_compra(limpio):
    from src.services import inteligencia
    from src.services.inteligencia import automatizacion as aut
    r = aut.procesar("stock_bajo", id_empresa=EMP, payload={"codigo": "LECHE", "stock": 2})
    assert r["ok"] and len(r["propuestas"]) == 1
    d = inteligencia.decisiones(EMP, usuario=GER)[0]
    assert d["titulo"] == "Crear propuesta de compra" and d["dominio"] == "compras"
    assert d["workflow_sugerido"] == "compras_pedido" and d["prioridad"] == "ALTA"


def test_dedup_propuestas_abiertas(limpio):
    from src.services.inteligencia import automatizacion as aut
    aut.procesar("proveedor_fallo", id_empresa=EMP, payload={"proveedor": "P1"})
    r2 = aut.procesar("proveedor_fallo", id_empresa=EMP, payload={"proveedor": "P1"})
    assert r2["propuestas"] == []          # ya propuesta abierta → no duplica


def test_todos_los_disparadores(limpio):
    from src.services import inteligencia
    from src.services.inteligencia import automatizacion as aut
    for disp, pl in (("stock_bajo", {"codigo": "A"}), ("mercancia_recibida", {"codigo": "B"}),
                     ("campana_finalizada", {"campana": "C1"}), ("precio_cambiado", {"codigo": "C"}),
                     ("proveedor_fallo", {"proveedor": "P"})):
        assert aut.procesar(disp, id_empresa=EMP, payload=pl)["propuestas"]
    assert len(inteligencia.decisiones(EMP, usuario=GER)) == 5
    assert set(aut.disparadores()) == {"stock_bajo", "mercancia_recibida", "campana_finalizada",
                                       "precio_cambiado", "proveedor_fallo"}


def test_evento_bus_mapea_a_disparador(limpio):
    from src.services import inteligencia
    from src.services.inteligencia import automatizacion as aut
    # Evento con mapeo → propone; evento sin mapeo → ignorado.
    r = aut.procesar_evento("STOCK_BAJO", id_empresa=EMP, payload={"codigo": "X"})
    assert r["propuestas"] and inteligencia.decisiones(EMP, usuario=GER)
    assert aut.procesar_evento("KARDEX_MOVIMIENTO", id_empresa=EMP, payload={})["ignorado"]


def test_solo_propone_no_ejecuta():
    from src.services.inteligencia import automatizacion as aut
    src = inspect.getsource(aut)
    # No modifica datos de negocio; reutiliza infra (no crea Scheduler/Workflow/Rules).
    for prohibido in ("UPDATE articulos", "INSERT INTO ventas", "class Scheduler", "class Workflow",
                      "class RulesEngine"):
        assert prohibido not in src
    d = aut.descriptor()
    assert d["solo_propone"] is True and d["modifica_datos"] is False and d["motor_nuevo"] is False
    assert set(d["reutiliza"]) >= {"eventbus", "scheduler", "workflow", "inteligencia"}


def test_evaluar_periodico_reutiliza_centro(limpio):
    from src.services.inteligencia import automatizacion as aut
    r = aut.evaluar_periodico(EMP, actor="scheduler")     # reutiliza inteligencia.generar
    assert r["ok"] and "generadas" in r and "circuitos_propuestos" in r
