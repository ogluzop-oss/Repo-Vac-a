"""
Tests · Autocobro · Asociación de cuenta de cliente.

Verifica `clientes.buscar_cliente_por_codigo` (resuelve por id / teléfono / email exacto, o única
coincidencia) — el resolvedor que usa el autocobro al escanear la tarjeta de cliente.
"""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture()
def cliente(db):
    from src.db import clientes as C
    from src.db.empresa import empresa_actual_id
    emp = empresa_actual_id()
    with db.obtener_conexion() as c:
        c.cursor().execute("DELETE FROM clientes WHERE telefono='600999888'")
        c.commit()
    cid = C.crear_cliente("Cliente Test", telefono="600999888", email="test@cli.com", id_empresa=emp)
    yield {"id": cid, "empresa": emp}
    with db.obtener_conexion() as c:
        c.cursor().execute("DELETE FROM clientes WHERE id=%s", (cid,))
        c.commit()


def test_por_codigo_id_telefono_email(cliente):
    from src.db.clientes import buscar_cliente_por_codigo
    emp = cliente["empresa"]
    assert buscar_cliente_por_codigo(str(cliente["id"]), id_empresa=emp)["id"] == cliente["id"]
    assert buscar_cliente_por_codigo("600999888", id_empresa=emp)["id"] == cliente["id"]
    assert buscar_cliente_por_codigo("test@cli.com", id_empresa=emp)["id"] == cliente["id"]


def test_por_codigo_desconocido(cliente):
    from src.db.clientes import buscar_cliente_por_codigo
    assert buscar_cliente_por_codigo("NO-EXISTE-XYZ", id_empresa=cliente["empresa"]) is None
    assert buscar_cliente_por_codigo("", id_empresa=cliente["empresa"]) is None
