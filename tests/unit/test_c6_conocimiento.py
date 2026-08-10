"""
Tests Etapa C · Fase C6: Conocimiento Empresarial (Área 7).

Verifica que el conocimiento busca/responde sobre el Centro Documental existente FILTRANDO por RBAC
(cada tipo de documento exige su permiso), devuelve referencias verificables, NUNCA inventa y es solo
lectura (no crea tablas ni motores).
"""

import inspect

import pytest

EMP = "T-KNW-A"
GER = {"id": "g", "perfil": "GERENTE"}     # ve contratos+facturas+pedidos
OPE = {"id": "o", "perfil": "OPERARIO"}    # solo ventas.ver → pedidos


@pytest.fixture()
def docs(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.db import documentos
    documentos.registrar_documento("/tmp/knw_contrato.pdf", tipo="contrato",
                                   nombre="Contrato de alquiler local", id_empresa=EMP)
    documentos.registrar_documento("/tmp/knw_factura.pdf", tipo="factura",
                                   nombre="Factura proveedor alquiler", id_empresa=EMP)
    documentos.registrar_documento("/tmp/knw_pedido.pdf", tipo="pedido",
                                   nombre="Pedido material alquiler", id_empresa=EMP)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_gerente_ve_todos_los_tipos(docs):
    from src.services.inteligencia import conocimiento
    res = conocimiento.buscar("alquiler", id_empresa=EMP, usuario=GER)
    tipos = {d["tipo"] for d in res}
    assert {"contrato", "factura", "pedido"} <= tipos      # autorizado para todos


def test_operario_solo_ve_autorizados(docs):
    from src.services.inteligencia import conocimiento
    res = conocimiento.buscar("alquiler", id_empresa=EMP, usuario=OPE)
    tipos = {d["tipo"] for d in res}
    assert "pedido" in tipos                                # ventas.ver
    assert "contrato" not in tipos and "factura" not in tipos  # rrhh.ver / contabilidad.ver → no


def test_filtro_por_tipo_no_autorizado(docs):
    from src.services.inteligencia import conocimiento
    # OPERARIO pide explícitamente contratos → no autorizado → vacío.
    assert conocimiento.buscar("alquiler", id_empresa=EMP, usuario=OPE, tipo="contrato") == []
    # GERENTE sí.
    assert conocimiento.buscar("alquiler", id_empresa=EMP, usuario=GER, tipo="contrato")


def test_responder_verificable_y_no_inventa(docs):
    from src.services.inteligencia import conocimiento
    r = conocimiento.responder("¿qué hay sobre el alquiler?", id_empresa=EMP, usuario=GER)
    assert r["verificable"] and r["documentos"]            # cita documentos reales
    # Pregunta sin documentación → no inventa.
    r2 = conocimiento.responder("informe sobre viajes a la luna", id_empresa=EMP, usuario=GER)
    assert r2["verificable"] is False and r2["documentos"] == []


def test_rbac_entrada_y_solo_lectura(docs):
    from src.services.inteligencia import conocimiento
    assert conocimiento.buscar("x", id_empresa=EMP, usuario={"id": "z", "perfil": "SIN"}) == []
    src = inspect.getsource(conocimiento)
    for prohibido in ("INSERT INTO", "UPDATE ", "CREATE TABLE", "DELETE FROM"):
        assert prohibido not in src
    d = conocimiento.descriptor()
    assert d["inventa"] is False and d["rbac_por_tipo"] is True and d["motor_nuevo"] is False
