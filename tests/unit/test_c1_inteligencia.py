"""
Tests Etapa C · Fase C1: Centro de Decisiones (capa transversal de inteligencia).

Verifica que el hub UNIFICA la capa IA existente en un ledger auditable de decisiones propuestas
(persistencia + dedup), gobernado por RBAC (ver/decidir), con aceptación/rechazo/feedback supervisado,
SIN modificar datos de negocio y SIN motor de IA paralelo (reutiliza `src.services.ia`).
"""

import inspect

import pytest

EMP = "T-INT-A"
GER = {"id": "g", "perfil": "GERENTE"}
OPE = {"id": "o", "perfil": "OPERARIO"}


def _fake_provider(id_empresa=None):
    from src.services.ia.modelos import Recomendacion
    return [Recomendacion("Reponer ART9", "stock bajo", "articulo", "ART9", "ALTA",
                          workflow="compras_pedido", datos={"codigo": "ART9", "stock": 2})]


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.services import inteligencia
    inteligencia.registrar_proveedor("test.prov", _fake_provider, tipo="recomendacion")
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_generar_persiste_y_deduplica(limpio):
    from src.services import inteligencia
    r = inteligencia.generar(EMP, proveedores=["test.prov"], actor="sistema")
    assert r["ok"] and r["generadas"] == 1
    # Segunda pasada: la propuesta ya abierta no se duplica.
    assert inteligencia.generar(EMP, proveedores=["test.prov"])["generadas"] == 0


def test_decisiones_y_justificacion_auditable(limpio):
    from src.services import inteligencia
    inteligencia.generar(EMP, proveedores=["test.prov"])
    decs = inteligencia.decisiones(EMP, usuario=GER)
    assert decs and decs[0]["titulo"] == "Reponer ART9" and decs[0]["prioridad"] == "ALTA"
    assert decs[0]["dominio"] == "inventario"
    d = inteligencia.obtener(decs[0]["id"], id_empresa=EMP, usuario=GER)
    assert d["datos"]["entidad_id"] == "ART9"       # justificación auditable (to_dict del proveedor)
    assert d["datos"]["datos"]["codigo"] == "ART9"  # datos originales del proveedor
    assert d["correlation_id"]                      # trazable (Decision Replay)


def test_rbac_ver_y_decidir(limpio):
    from src.services import inteligencia
    inteligencia.generar(EMP, proveedores=["test.prov"])
    did = inteligencia.decisiones(EMP, usuario=GER)[0]["id"]
    # OPERARIO VE pero NO decide.
    assert inteligencia.decisiones(EMP, usuario=OPE)          # ver ok
    assert inteligencia.aceptar(did, usuario=OPE, id_empresa=EMP)["ok"] is False
    # GERENTE decide.
    assert inteligencia.aceptar(did, usuario=GER, id_empresa=EMP)["ok"] is True
    # Ya no aparece como propuesta.
    assert not [x for x in inteligencia.decisiones(EMP, usuario=GER) if x["id"] == did]


def test_rechazar_y_feedback(limpio):
    from src.services import inteligencia
    inteligencia.generar(EMP, proveedores=["test.prov"])
    did = inteligencia.decisiones(EMP, usuario=GER)[0]["id"]
    assert inteligencia.feedback(did, util=True, comentario="acertada", usuario=GER,
                                 id_empresa=EMP)["ok"]
    assert inteligencia.rechazar(did, motivo="ya repuesto", usuario=GER, id_empresa=EMP)["ok"]
    d = inteligencia.obtener(did, id_empresa=EMP, usuario=GER)
    assert d["estado"] == "rechazada"


def test_resumen_ejecutivo(limpio):
    from src.services import inteligencia
    inteligencia.generar(EMP, proveedores=["test.prov"])
    res = inteligencia.resumen(EMP, usuario=GER)
    assert res["total"] == 1 and res["por_prioridad"].get("ALTA") == 1
    assert res["por_dominio"].get("inventario") == 1


def test_reutiliza_ia_sin_motor_paralelo():
    from src.services import inteligencia
    src = inspect.getsource(inteligencia)
    # Reutiliza la capa IA existente como proveedores; no reimplementa la IA.
    assert "src.services.ia" in src
    for redef in ("def generar_recomendaciones", "def detectar_anomalias", "class IAService"):
        assert redef not in src
    d = inteligencia.descriptor()
    assert d["motor_ia_nuevo"] is False and d["modifica_datos"] is False and d["capa"] == "transversal"
    assert set(d["proveedores"]) >= {"ia.recomendaciones", "ia.anomalias", "ia.riesgos",
                                     "ia.predicciones"}


def test_no_modifica_datos_de_negocio():
    from src.services import inteligencia
    codigo = "\n".join(l for l in inspect.getsource(inteligencia).splitlines()
                       if not l.lstrip().startswith("#"))
    # Solo escribe en su propio ledger `decisiones_ia`; no toca tablas de dominio.
    for prohibido in ("UPDATE articulos", "INSERT INTO ventas", "UPDATE stock", "DELETE FROM articulos"):
        assert prohibido not in codigo
