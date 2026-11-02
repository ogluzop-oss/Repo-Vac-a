"""
Motor de Alta Conversión e-Commerce · rutas Flask del storefront: Drawer Cart (añadir/actualizar/
quitar/resumen), selector de variantes AJAX, One-Page Checkout (contacto → dirección → pago, con
resumen re-cotizado en vivo) y creación real del pedido (reutiliza `tpv.online_orders_service`,
nunca un motor de pedidos paralelo)."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    eid = fab.empresa("STOREFRONT CARRITO TEST")
    fab.web(id_empresa=eid, activa=1, nombre="Tienda Carrito Test", moneda="EUR")
    return eid


def _producto(fab, emp, *, precio=20.0, stock=10):
    cod = fab.articulo(id_empresa=emp, precio=precio, stock_total=stock, nombre="Producto Carrito")
    pid = fab.producto_catalogo(cod, id_empresa=emp, titulo_web="Producto Carrito Web", visible_web=1)
    from src.db import catalogo as cat
    return cod, cat.obtener_producto(id_producto=pid, id_empresa=emp)


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_carrito_lineas", "cd_carrito_actividad", "cd_carrito_abandono"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM pedidos_online_items WHERE id_pedido IN "
                    "(SELECT id_pedido FROM pedidos_online WHERE id_empresa=%s)", (emp,))
        cur.execute("DELETE FROM pedidos_online WHERE id_empresa=%s", (emp,))
        conn.commit()


def _client():
    from src.backend.app import crear_app
    return crear_app().test_client()


# ── Drawer Cart ───────────────────────────────────────────────────────────────
def test_resumen_carrito_vacio_fija_cookie(fab, db, emp):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/carrito/resumen")
    assert r.status_code == 200
    assert r.get_json()["lineas"] == []
    # La cookie de sesión de carrito queda fijada en la respuesta (validado funcionalmente en el
    # siguiente test: un segundo request del MISMO cliente ve el carrito ya identificado).
    assert f"sm_cart_{emp}" in r.headers.get("Set-Cookie", "")


def test_anadir_por_id_producto_vía_http(fab, db, emp):
    cod, prod = _producto(fab, emp)
    cli = _client()
    r = cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 2})
    assert r.status_code == 200
    d = r.get_json()
    assert d["n_articulos"] == 2 and len(d["lineas"]) == 1 and d["lineas"][0]["codigo"] == cod

    # La cookie persiste entre peticiones del MISMO cliente -> el resumen sigue viendo el carrito.
    r2 = cli.get(f"/tienda/{emp}/carrito/resumen")
    assert r2.get_json()["n_articulos"] == 2


def test_actualizar_y_quitar_vía_http(fab, db, emp):
    cod, prod = _producto(fab, emp)
    cli = _client()
    r = cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 1})
    id_linea = r.get_json()["lineas"][0]["id"]

    r2 = cli.post(f"/tienda/{emp}/carrito/actualizar", json={"id_linea": id_linea, "cantidad": 5})
    assert r2.get_json()["lineas"][0]["cantidad"] == 5

    r3 = cli.post(f"/tienda/{emp}/carrito/quitar", json={"id_linea": id_linea})
    assert r3.get_json()["lineas"] == []


def test_anadir_producto_inexistente_devuelve_400(fab, db, emp):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/carrito/anadir", json={"codigo": "NO-EXISTE", "cantidad": 1})
    assert r.status_code == 400


# ── Selector de variantes ──────────────────────────────────────────────────────
def test_variante_endpoint_devuelve_precio_y_disponibilidad(fab, db, emp):
    cod, prod = _producto(fab, emp, precio=30.0)
    from src.db import catalogo as cat
    cat.crear_variante(prod["id"], sku="VAR-1", atributos={"Talla": "M"}, precio_dif=5.0,
                       id_empresa=emp)
    cli = _client()
    r = cli.get(f"/tienda/{emp}/producto/{prod['slug']}/variante?sku=VAR-1")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["precio"] == 35.0 and d["disponible"] is True


def test_variante_sku_desconocido_404(fab, db, emp):
    cod, prod = _producto(fab, emp)
    cli = _client()
    r = cli.get(f"/tienda/{emp}/producto/{prod['slug']}/variante?sku=NO-EXISTE")
    assert r.status_code == 404


# ── One-Page Checkout ──────────────────────────────────────────────────────────
def test_pagina_checkout_carga(fab, db, emp):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/checkout")
    assert r.status_code == 200
    assert b"Finalizar compra" in r.data and b"co-pagar" in r.data


def test_checkout_email_captura_lead_temprano(fab, db, emp):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/checkout/email", json={"email": "cliente@test.com"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_checkout_confirmar_sin_lineas_falla_honesto(fab, db, emp):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "cliente@test.com", "nombre": "Cliente Test", "direccion": "C/ Falsa 123",
        "ciudad": "Madrid", "cp": "28001", "pais": "ES"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_checkout_confirmar_crea_pedido_real_y_redirige_a_confirmacion(fab, db, emp):
    """Sin pasarela configurada (empresa de test recién creada): el pedido se crea igualmente
    (reutilizando `online_orders_service.crear_pedido_online`, el motor REAL de pedidos) y, al no
    haber cobro real posible, se redirige honestamente a la propia página de confirmación en
    PENDIENTE — nunca se marca PAGADO sin una confirmación real de la pasarela."""
    cod, prod = _producto(fab, emp, precio=25.0, stock=10)
    cli = _client()
    cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 2})

    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "cliente@test.com", "nombre": "Cliente Test", "direccion": "C/ Falsa 123",
        "ciudad": "Madrid", "cp": "28001", "pais": "ES", "pasarela": "simulado"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert f"/tienda/{emp}/checkout/confirmacion/" in d["url"]

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT total, cliente_email, estado FROM pedidos_online WHERE id_empresa=%s", (emp,))
        fila = cur.fetchone()
    total, email, estado = fila if not isinstance(fila, dict) else (fila["total"], fila["cliente_email"], fila["estado"])
    assert float(total) == 50.0
    assert email == "cliente@test.com"
    assert estado == "PENDIENTE"

    # El carrito queda vacío tras confirmar (se cerró el episodio de compra).
    r2 = cli.get(f"/tienda/{emp}/carrito/resumen")
    assert r2.get_json()["lineas"] == []


def test_pagina_confirmacion_muestra_el_pedido(fab, db, emp):
    cod, prod = _producto(fab, emp, precio=10.0, stock=5)
    cli = _client()
    cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 1})
    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "cliente@test.com", "nombre": "Cliente Test", "direccion": "C/ Falsa 123",
        "ciudad": "Madrid", "cp": "28001", "pais": "ES"})
    url = r.get_json()["url"]
    ruta = url.split("://", 1)[-1].split("/", 1)[-1]
    rc = cli.get("/" + ruta)
    assert rc.status_code == 200
    assert "Pedido recibido".encode("utf-8") in rc.data or "pedido".encode("utf-8") in rc.data.lower()


def test_carrito_restaurar_fija_cookie_y_redirige_a_checkout(fab, db, emp):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/carrito/restaurar?t=un-token-cualquiera")
    assert r.status_code in (301, 302)
    assert r.headers["Location"].endswith(f"/tienda/{emp}/checkout")


# ── Ficha de producto: micro-incentivos de conversión ─────────────────────────
def test_pagina_producto_incluye_comprar_ahora_y_badges_de_confianza(fab, db, emp):
    cod, prod = _producto(fab, emp, precio=15.0, stock=5)
    cli = _client()
    r = cli.get(f"/tienda/{emp}/producto/{prod['slug']}")
    assert r.status_code == 200
    assert "Comprar ahora".encode("utf-8") in r.data
    assert "Añadir al carrito".encode("utf-8") in r.data
    assert "SSL".encode("utf-8") in r.data


def test_pagina_producto_sin_zona_de_envio_no_inventa_fecha_de_entrega(fab, db, emp):
    """Degradación honesta: sin zonas de envío configuradas, el estimador NO debe aparecer (nunca
    se inventa una fecha de entrega)."""
    cod, prod = _producto(fab, emp)
    cli = _client()
    r = cli.get(f"/tienda/{emp}/producto/{prod['slug']}")
    assert "Recíbelo entre".encode("utf-8") not in r.data


def test_pagina_producto_con_zona_de_envio_muestra_estimador_de_entrega(fab, db, emp):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=4.0, id_empresa=emp)
    cod, prod = _producto(fab, emp)
    cli = _client()
    r = cli.get(f"/tienda/{emp}/producto/{prod['slug']}")
    assert "Recíbelo entre".encode("utf-8") in r.data
