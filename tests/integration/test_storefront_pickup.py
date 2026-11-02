"""
Click & Collect (Generador de Apps Móviles PWA, Fase 4) — rutas Flask del storefront: selector de
tienda en el checkout, reserva + pago reutilizando el motor omnicanal `comercio_digital.pickup`
(en vez de `online_orders_service`, que sigue sirviendo el envío a domicilio sin cambios), página
de confirmación, listado "Mis recogidas" y cancelación voluntaria con reembolso inmediato.
"""

import uuid

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    eid = fab.empresa("STOREFRONT PICKUP TEST")
    fab.web(id_empresa=eid, activa=1, nombre="Tienda Pickup Test", moneda="EUR")
    return eid


def _tienda(fab, emp, nombre=None):
    nombre = nombre or f"Tienda Pickup {uuid.uuid4().hex[:8]}"
    tid = fab._exec(
        "INSERT INTO tiendas (nombre, activo, id_empresa, codigo_tienda) VALUES (%s,1,%s,%s)",
        (nombre, emp, nombre[:20]))
    fab._borrar("tiendas", "id", tid)
    return tid, nombre


def _producto(fab, emp, *, precio=20.0, stock=10):
    cod = fab.articulo(id_empresa=emp, precio=precio, stock_total=stock, stock_tienda=stock,
                       nombre="Producto Pickup")
    pid = fab.producto_catalogo(cod, id_empresa=emp, titulo_web="Producto Pickup Web", visible_web=1)
    from src.db import catalogo as cat
    return cod, cat.obtener_producto(id_producto=pid, id_empresa=emp)


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_reservas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM cd_pagos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM transaccion_lineas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM transaccion_comercial WHERE id_empresa=%s", (emp,))
        for t in ("cd_carrito_lineas", "cd_carrito_actividad", "cd_carrito_abandono"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM cd_clientes_sesiones WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM clientes WHERE id_empresa=%s", (emp,))
        conn.commit()


def _client():
    from src.backend.app import crear_app
    return crear_app().test_client()


def _mockear_envio(monkeypatch, enviados):
    monkeypatch.setattr("src.db.correo.listar_correos",
                        lambda eid: [{"id_correo": "buzon-fake", "estado": "activo"}])
    monkeypatch.setattr(
        "src.services.correo.servicio.enviar_documento",
        lambda id_correo, dest, asunto, cuerpo="", adjuntos=None:
            (enviados.append((dest, asunto, cuerpo)) or (True, "ok")))


def _sesion_cliente(cli, emp, enviados, email):
    r1 = cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": email})
    assert r1.status_code == 200
    token = enviados[-1][2].split("?t=", 1)[1].split("\n", 1)[0].strip()
    r2 = cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t={token}")
    assert r2.status_code in (301, 302)


def test_tiendas_endpoint_tenant_filtrado(fab, db, emp):
    _tid, nombre = _tienda(fab, emp)
    otra = fab.empresa("OTRA EMPRESA PICKUP")
    fab.web(id_empresa=otra, activa=1, nombre="Otra Tienda")
    _tienda(fab, otra, nombre="Tienda De Otra Empresa")

    cli = _client()
    r = cli.get(f"/tienda/{emp}/tiendas")
    assert r.status_code == 200
    nombres = [t["nombre"] for t in r.get_json()]
    assert nombre in nombres
    assert "Tienda De Otra Empresa" not in nombres


def test_checkout_confirmar_pickup_sin_tienda_falla_honesto(fab, db, emp):
    cod, prod = _producto(fab, emp)
    cli = _client()
    cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 1})
    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "cliente@test.com", "nombre": "Cliente Test", "modo_entrega": "pickup"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_checkout_confirmar_pickup_crea_reserva_pagada_y_confirmacion(fab, db, emp):
    tid, _nombre = _tienda(fab, emp)
    cod, prod = _producto(fab, emp, precio=15.0, stock=3)
    cli = _client()
    cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 2})

    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "pickup@test.com", "nombre": "Cliente Pickup", "modo_entrega": "pickup",
        "id_tienda": tid, "pasarela": "simulado"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert f"/tienda/{emp}/pickup/confirmacion/" in d["url"]

    ruta = "/" + d["url"].split("://", 1)[-1].split("/", 1)[-1]
    rc = cli.get(ruta)
    assert rc.status_code == 200
    assert "Reserva confirmada".encode("utf-8") in rc.data

    id_tx = ruta.rsplit("/", 1)[-1]
    from src.services.comercio_digital import transacciones as _tx_svc
    tx = _tx_svc.obtener(id_tx, emp)
    assert tx["estado"] == "PAGADA"
    assert float(tx["total"]) == 30.0

    # El carrito queda vacío tras confirmar, igual que en el checkout de envío a domicilio.
    r2 = cli.get(f"/tienda/{emp}/carrito/resumen")
    assert r2.get_json()["lineas"] == []


def test_recogidas_lista_y_cancelar_reembolsa(fab, db, emp, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    tid, _nombre = _tienda(fab, emp)
    cod, prod = _producto(fab, emp, precio=10.0, stock=5)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "recogidas@test.com")
    cli.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 1})

    r = cli.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "recogidas@test.com", "nombre": "Cliente Recogidas", "modo_entrega": "pickup",
        "id_tienda": tid, "pasarela": "simulado"})
    id_tx = r.get_json()["url"].rsplit("/", 1)[-1]

    rl = cli.get(f"/tienda/{emp}/cuenta/recogidas")
    assert rl.status_code == 200
    assert "Lista para recoger".encode("utf-8") in rl.data
    assert f"/cuenta/recogidas/{id_tx}/cancelar".encode("utf-8") in rl.data

    rc = cli.post(f"/tienda/{emp}/cuenta/recogidas/{id_tx}/cancelar")
    assert rc.status_code in (301, 302)

    from src.services.comercio_digital import transacciones as _tx_svc
    tx = _tx_svc.obtener(id_tx, emp)
    assert tx["estado"] == "CANCELADA"


def test_no_se_puede_cancelar_la_recogida_de_otro_cliente(fab, db, emp, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    tid, _nombre = _tienda(fab, emp)
    cod, prod = _producto(fab, emp, precio=10.0, stock=5)

    dueno = _client()
    _sesion_cliente(dueno, emp, enviados, "dueno@test.com")
    dueno.post(f"/tienda/{emp}/carrito/anadir", json={"id_producto": prod["id"], "cantidad": 1})
    r = dueno.post(f"/tienda/{emp}/checkout/confirmar", json={
        "email": "dueno@test.com", "nombre": "Dueno", "modo_entrega": "pickup",
        "id_tienda": tid, "pasarela": "simulado"})
    id_tx = r.get_json()["url"].rsplit("/", 1)[-1]

    intruso = _client()
    _sesion_cliente(intruso, emp, enviados, "intruso_pickup@test.com")
    intruso.post(f"/tienda/{emp}/cuenta/recogidas/{id_tx}/cancelar")

    from src.services.comercio_digital import transacciones as _tx_svc
    tx = _tx_svc.obtener(id_tx, emp)
    assert tx["estado"] == "PAGADA"
