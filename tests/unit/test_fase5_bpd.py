"""
Tests Fase V · Bloque 4: Business Process Designer.

Verifica: paleta de bloques, diseño VERSIONADO (borrador/publicado/rollback), validación del grafo,
compilación al Workflow Engine EXISTENTE (no un motor nuevo) y aislamiento multiempresa.
"""

import pytest

EMP = "T-BPD-A"
EMP_B = "T-BPD-B"


@pytest.fixture
def limpio(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bpd_versiones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            cur.execute("DELETE FROM bpd_procesos WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            conn.commit()
    _b(); yield; _b()


def _diseno():
    return {"nodos": [{"id": "n1", "tipo": "inicio"},
                      {"id": "n2", "tipo": "aprobacion"},
                      {"id": "n3", "tipo": "firma"},
                      {"id": "n4", "tipo": "enviar_comunicacion"},
                      {"id": "n5", "tipo": "fin"}],
            "aristas": [{"desde": "n1", "hasta": "n2"}, {"desde": "n2", "hasta": "n3"},
                        {"desde": "n3", "hasta": "n4"}, {"desde": "n4", "hasta": "n5"}]}


def test_paleta_bloques():
    from src.services import bpd
    tipos = {b["tipo"] for b in bpd.paleta()}
    assert {"inicio", "fin", "aprobacion", "firma", "enviar_comunicacion", "regla",
            "workflow_hijo"} <= tipos
    # Cada bloque mapea a un servicio existente (no lógica nueva).
    assert bpd.destino("aprobacion").startswith("workflow")
    assert bpd.destino("enviar_comunicacion").startswith("ccp")


def test_validacion_diseno():
    from src.services import bpd
    ok, _ = bpd.validar_definicion(_diseno())
    assert ok
    # Sin inicio/fin → inválido.
    malo = {"nodos": [{"id": "x", "tipo": "aprobacion"}], "aristas": []}
    ok2, errores = bpd.validar_definicion(malo)
    assert not ok2 and any("inicio" in e for e in errores)


def test_versionado_y_publicacion(limpio):
    from src.services import bpd
    pid = bpd.crear_proceso("flujo_factura", "Flujo factura", id_empresa=EMP)
    assert pid
    v1 = bpd.guardar_borrador(pid, _diseno(), id_empresa=EMP)
    assert v1["ok"] and v1["version"] == 1
    v2 = bpd.guardar_borrador(pid, _diseno(), id_empresa=EMP)
    assert v2["version"] == 2
    assert bpd.publicar(pid, 2, id_empresa=EMP)["ok"]
    # Rollback a v1.
    assert bpd.rollback(pid, 1, id_empresa=EMP)["ok"]
    proc = next(p for p in bpd.listar_procesos(EMP) if p["id"] == pid)
    assert proc["version_actual"] == 1 and proc["estado"] == "publicado"


def test_compilacion_reusa_workflow(limpio):
    from src.services import bpd
    pid = bpd.crear_proceso("flujo_c", "Flujo C", id_empresa=EMP)
    bpd.guardar_borrador(pid, _diseno(), id_empresa=EMP)
    comp = bpd.compilar_proceso(pid, id_empresa=EMP)
    assert comp["ok"] and comp["motor"] == "workflow"        # reutiliza el Workflow Engine
    tipos = [p["tipo"] for p in comp["pasos"]]
    assert "aprobacion" in tipos and "inicio" not in tipos    # inicio/fin no son pasos ejecutables


def test_aislamiento_empresa(limpio):
    from src.services import bpd
    bpd.crear_proceso("solo_a", "Solo A", id_empresa=EMP)
    claves_a = {p["clave"] for p in bpd.listar_procesos(EMP)}
    claves_b = {p["clave"] for p in bpd.listar_procesos(EMP_B)}
    assert "solo_a" in claves_a and "solo_a" not in claves_b   # 0 cruces
