"""
Tests PCD · Fase 4 (RFC-CD-005): Fulfillment Engine + Plan de Cumplimiento.

Verifica el CONTRATO del dominio: Plan de Cumplimiento como objeto ESTABLE e INMUTABLE + VERSIONADO;
SCORE por alternativa; contrato Strategy → Evaluator → Plan con varios evaluadores; consumo del
RESULTADO de Availability (sin llamada directa entre motores); Fulfillment depende SOLO de
capacidades (no Rules ni Availability); no crea reservas ni mueve stock; integración con el historial
de decisiones (Audit Replay).
"""

import dataclasses
import inspect

import pytest


def _disp(cantidad=3, buckets=None):
    return {"codigo": "X", "cantidad_solicitada": cantidad,
            "buckets": buckets or [
                {"bucket": "central", "ubicacion": "central", "disponible": 5, "eta_dias": 2},
                {"bucket": "otras_tiendas", "ubicacion": "TND-2", "id_tienda": 2,
                 "disponible": 5, "eta_dias": 0}]}


def test_plan_es_objeto_estable_e_inmutable():
    from src.services.comercio_digital.inventario import fulfillment as ff
    plan = ff.planificar(_disp(), estrategia="equilibrado")
    assert isinstance(plan, ff.PlanCumplimiento)          # objeto de dominio, no JSON ad hoc
    # Inmutable (frozen dataclass).
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.version = 99
    d = plan.as_dict()
    assert set(d) >= {"version", "estrategia", "origen_elegido", "alternativas", "reglas_aplicadas",
                      "pesos", "prioridad_empresarial", "cubre"}


def test_score_y_alternativas_con_motivo():
    from src.services.comercio_digital.inventario import fulfillment as ff
    plan = ff.planificar(_disp(), estrategia="equilibrado")
    assert plan.origen_elegido["score"] is not None       # SCORE en el elegido
    assert plan.alternativas and all("score" in a and "motivo_descarte" in a
                                     for a in plan.alternativas)
    assert plan.cubre is True


def test_strategy_evaluator_plan():
    from src.services.comercio_digital.inventario import fulfillment as ff
    d = _disp()   # central (eta 2, coste 1) vs otras (eta 0, coste 2)
    assert set(ff.evaluadores.estrategias()) >= {"equilibrado", "coste", "rapidez", "ia"}
    # Coste → el más barato (central); Rapidez → el más rápido (otras).
    assert ff.planificar(d, estrategia="coste").origen_elegido["bucket"] == "central"
    assert ff.planificar(d, estrategia="rapidez").origen_elegido["bucket"] == "otras_tiendas"


def test_prioridad_empresarial():
    from src.services.comercio_digital.inventario import fulfillment as ff
    d = _disp()
    # Sin prioridad, equilibrado elige otras_tiendas (más rápido).
    assert ff.planificar(d, estrategia="equilibrado").origen_elegido["bucket"] == "otras_tiendas"
    # "vaciar:central" bonifica central → pasa a ser el elegido.
    plan = ff.planificar(d, estrategia="equilibrado", contexto={"prioridad": "vaciar:central"})
    assert plan.origen_elegido["bucket"] == "central" and plan.prioridad_empresarial == "vaciar:central"


def test_inmutable_versionado_replanificar():
    from src.services.comercio_digital.inventario import fulfillment as ff
    p1 = ff.planificar(_disp(), estrategia="equilibrado", version=1)
    p2 = ff.replanificar(p1, _disp(cantidad=1), contexto={"prioridad": "vaciar:central"})
    assert p1.version == 1 and p2.version == 2 and p1 is not p2   # nuevo plan, no mutación
    assert p2.prioridad_empresarial == "vaciar:central"


def test_fulfillment_solo_capacidades_no_availability_ni_rules():
    from src.services.comercio_digital.inventario import fulfillment as ff
    src = inspect.getsource(ff) + inspect.getsource(ff.evaluadores)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for prohibido in ("from src.services.rules", "import rules", "availability"):
        assert not any(prohibido in l for l in imports), f"Fulfillment acopla a {prohibido}"
    # Consume capacidades (Rules/IA) por la fachada.
    assert "capabilities" in src
    # No escribe (no crea reservas ni mueve stock).
    codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for w in ("INSERT ", "UPDATE ", "DELETE ", "obtener_conexion"):
        assert w not in codigo


def test_composicion_resolver():
    """`inventario.resolver` es el ÚNICO punto que combina Availability + Fulfillment."""
    from src.services.comercio_digital import inventario as inv
    plan = inv.resolver("NOEXISTE", cantidad=1, estrategia="equilibrado", id_empresa="T-FF-A")
    from src.services.comercio_digital.inventario import fulfillment as ff
    assert isinstance(plan, ff.PlanCumplimiento)   # compone aunque no haya stock (plan sin cubrir)
    assert plan.cubre is False


def test_plan_en_audit_replay(db):
    """El Plan se registra en transaccion_decisiones (motor=fulfillment) → reconstruible (N9)."""
    from src.services.comercio_digital import transacciones as tx
    from src.services.comercio_digital.inventario import fulfillment as ff
    EMP = "T-FF-A"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
    tid = tx.crear(id_empresa=EMP, lineas=[{"codigo": "X", "cantidad": 1, "precio_unitario": 1}])
    plan = ff.planificar(_disp(cantidad=1), estrategia="coste")
    assert tx.registrar_decision(tid, motor="fulfillment", decision="plan v1",
                                 resultado=plan.as_dict(), actor="motor", id_empresa=EMP)
    rec = tx.reconstruir(tid, EMP)
    dec = rec["decisiones"][0]
    assert dec["motor"] == "fulfillment"
    import json
    assert json.loads(dec["resultado"])["estrategia"] == "coste"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
