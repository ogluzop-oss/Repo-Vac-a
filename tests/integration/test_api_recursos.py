"""Integración · API A1.2: endpoints read-only de catálogo/pedidos + aislamiento tenant."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


def _token(db, fab, nombre, id_empresa=None):
    u = fab.usuario(nombre=nombre, password="Clave_Api_123456", perfil="ADMINISTRADOR",
                    id_empresa=id_empresa)
    # Contrato actual: el campo de empresa en el body de login es `id_empresa` (igual que el
    # cliente móvil), y `usuario` en la respuesta es el nombre (string), no un objeto con `.id`.
    body = {"usuario": nombre, "password": "Clave_Api_123456"}
    if id_empresa:
        body["id_empresa"] = id_empresa
    from src.backend.app import crear_app
    cli = crear_app().test_client()
    r = cli.post("/api/v1/auth/login", json=body)
    tok = r.get_json()["access"]
    fab.al_limpiar(lambda: _borra_sesiones(db, u["id"]))
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_listar_productos_requiere_token(cliente):
    assert cliente.get("/api/v1/catalogo/productos").status_code == 401


def test_catalogo_aislado_por_tenant(db, fab, cliente):
    emp_b = fab.empresa("EMP API REC B")
    # Datos SOLO en empresa B.
    cod_b = fab.articulo(id_empresa=emp_b, nombre="ArtAPI B")
    fab.producto_catalogo(cod_b, id_empresa=emp_b, titulo_web="Prod API B", visible_web=1)

    tok_a = _token(db, fab, "API_REC_A")               # empresa por defecto (A)
    tok_b = _token(db, fab, "API_REC_B", id_empresa=emp_b)

    # Productos: A no ve los de B; B sí.
    prods_a = cliente.get("/api/v1/catalogo/productos", headers=_h(tok_a)).get_json()["productos"]
    prods_b = cliente.get("/api/v1/catalogo/productos", headers=_h(tok_b)).get_json()["productos"]
    cods_a = {p.get("codigo_articulo") for p in prods_a}
    cods_b = {p.get("codigo_articulo") for p in prods_b}
    assert cod_b in cods_b and cod_b not in cods_a


@pytest.mark.skip(reason="/api/v1/pedidos (pedidos online legacy) se retiró al fusionar las dos APIs "
                         "/api/v1 (ver ADR-0001); su sucesor /commerce usa un modelo de datos "
                         "distinto (Transacción Comercial), no un puerto directo de este endpoint.")
def test_pedidos_aislados_por_tenant_OBSOLETO(db, fab, cliente):
    pass


def test_categorias_endpoint(db, fab, cliente):
    fab.categoria("Cat API")
    tok = _token(db, fab, "API_REC_CAT")
    r = cliente.get("/api/v1/catalogo/categorias", headers=_h(tok))
    assert r.status_code == 200 and "categorias" in r.get_json()


@pytest.mark.skip(reason="/api/v1/pedidos (pedidos online legacy) se retiró al fusionar las dos APIs "
                         "/api/v1 (ver ADR-0001); no hay puerto directo, ver "
                         "test_pedidos_aislados_por_tenant_OBSOLETO. La red anti-secretos "
                         "(_sin_secretos) SÍ se portó y cubre customers/suppliers/orders/stock/etc.")
def test_sanitizacion_lista_blanca_pedido_OBSOLETO(db, fab, cliente):
    pass


def _borra_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()
