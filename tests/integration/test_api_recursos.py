"""Integración · API A1.2: endpoints read-only de catálogo/pedidos + aislamiento tenant."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


def _token(db, fab, nombre, id_empresa=None):
    fab.usuario(nombre=nombre, password="Clave_Api_123456", perfil="ADMINISTRADOR",
                id_empresa=id_empresa)
    body = {"usuario": nombre, "password": "Clave_Api_123456"}
    if id_empresa:
        body["empresa"] = id_empresa
    from src.backend.app import crear_app
    cli = crear_app().test_client()
    r = cli.post("/api/v1/auth/login", json=body)
    tok = r.get_json()["access"]
    fab.al_limpiar(lambda: _borra_sesiones(db, r.get_json()["usuario"]["id"]))
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_listar_productos_requiere_token(cliente):
    assert cliente.get("/api/v1/catalogo/productos").status_code == 401


def test_catalogo_y_pedidos_aislados_por_tenant(db, fab, cliente):
    emp_b = fab.empresa("EMP API REC B")
    # Datos SOLO en empresa B.
    cod_b = fab.articulo(id_empresa=emp_b, nombre="ArtAPI B")
    fab.producto_catalogo(cod_b, id_empresa=emp_b, titulo_web="Prod API B", visible_web=1)
    ped_b = fab.pedido_online(id_empresa=emp_b, total=33.0)

    tok_a = _token(db, fab, "API_REC_A")               # empresa por defecto (A)
    tok_b = _token(db, fab, "API_REC_B", id_empresa=emp_b)

    # Productos: A no ve los de B; B sí.
    prods_a = cliente.get("/api/v1/catalogo/productos", headers=_h(tok_a)).get_json()["productos"]
    prods_b = cliente.get("/api/v1/catalogo/productos", headers=_h(tok_b)).get_json()["productos"]
    cods_a = {p.get("codigo_articulo") for p in prods_a}
    cods_b = {p.get("codigo_articulo") for p in prods_b}
    assert cod_b in cods_b and cod_b not in cods_a

    # Pedidos: A no ve el pedido de B; B sí.
    peds_a = cliente.get("/api/v1/pedidos", headers=_h(tok_a)).get_json()["pedidos"]
    peds_b = cliente.get("/api/v1/pedidos", headers=_h(tok_b)).get_json()["pedidos"]
    assert ped_b not in {p["id_pedido"] for p in peds_a}
    assert ped_b in {p["id_pedido"] for p in peds_b}

    # Acceso directo cruzado a un pedido de B desde A → 404 (aislamiento).
    assert cliente.get(f"/api/v1/pedidos/{ped_b}", headers=_h(tok_a)).status_code == 404
    assert cliente.get(f"/api/v1/pedidos/{ped_b}", headers=_h(tok_b)).status_code == 200


def test_categorias_endpoint(db, fab, cliente):
    fab.categoria("Cat API")
    tok = _token(db, fab, "API_REC_CAT")
    r = cliente.get("/api/v1/catalogo/categorias", headers=_h(tok))
    assert r.status_code == 200 and "categorias" in r.get_json()


def test_sanitizacion_lista_blanca_pedido(db, fab, cliente):
    # Pedido con referencia de pago (campo interno que NO debe exponerse).
    pid = fab.pedido_online(total=12.0, referencia_pago="cs_secreto_interno")
    tok = _token(db, fab, "API_SANEA")
    r = cliente.get(f"/api/v1/pedidos/{pid}", headers=_h(tok))
    assert r.status_code == 200
    j = r.get_json()
    # Lista blanca: referencia_pago / enlace_pago / estado_pago-interno no se exponen.
    assert "referencia_pago" not in j and "enlace_pago" not in j
    # Red anti-secretos: ninguna clave con subcadena sensible.
    prohibidas = ("secret", "token", "clave", "hash", "password", "api_key")
    assert not any(any(s in str(k).lower() for s in prohibidas) for k in j)


def _borra_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()
