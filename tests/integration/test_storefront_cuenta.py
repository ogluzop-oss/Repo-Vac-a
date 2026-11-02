"""
Cuenta del cliente (Generador de Apps Móviles PWA, Fase 2) — rutas Flask del storefront: Magic
Link (solicitar/confirmar), perfil editable, cerrar sesión. Reutiliza `services.comercio_digital.
clientes_auth`/`db.clientes` — ya probados a nivel de servicio en `test_clientes_auth.py`; aquí se
cubre la capa HTTP (cookies, redirecciones, formularios)."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    eid = fab.empresa("STOREFRONT CUENTA TEST")
    fab.web(id_empresa=eid, activa=1, nombre="Tienda Cuenta Test")
    return eid


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
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


def test_cuenta_sin_sesion_redirige_a_entrar(emp, db):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/cuenta")
    assert r.status_code in (301, 302)
    assert r.headers["Location"].endswith(f"/tienda/{emp}/cuenta/entrar")


def test_pagina_entrar_carga(emp, db):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/cuenta/entrar")
    assert r.status_code == 200
    assert b"Accede a tu cuenta" in r.data


def test_solicitar_magic_link_sin_buzon_muestra_error_honesto(emp, db):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": "comprador@test.com"})
    assert r.status_code == 200
    assert "no tiene el correo configurado".encode("utf-8") in r.data


def test_flujo_completo_magic_link_http(emp, db, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()

    r1 = cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": "comprador@test.com"})
    assert r1.status_code == 200
    assert "enlace de acceso".encode("utf-8") in r1.data
    assert len(enviados) == 1

    cuerpo = enviados[0][2]
    token = cuerpo.split("?t=", 1)[1].split("\n", 1)[0].strip()

    r2 = cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t={token}")
    assert r2.status_code in (301, 302)
    assert r2.headers["Location"].endswith(f"/tienda/{emp}/cuenta")

    # La cookie de sesión persiste en el MISMO cliente -> /cuenta ya no redirige.
    r3 = cli.get(f"/tienda/{emp}/cuenta")
    assert r3.status_code == 200
    assert b"comprador@test.com" in r3.data


def test_confirmar_enlace_invalido_muestra_error(emp, db):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t=token-invalido")
    assert r.status_code == 200
    assert "no es v".encode("utf-8") in r.data or "caducado".encode("utf-8") in r.data


def test_actualizar_perfil_y_cerrar_sesion(emp, db, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": "perfil@test.com"})
    cuerpo = enviados[0][2]
    token = cuerpo.split("?t=", 1)[1].split("\n", 1)[0].strip()
    cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t={token}")

    r = cli.post(f"/tienda/{emp}/cuenta", data={
        "nombre": "Nombre Actualizado", "email": "perfil@test.com",
        "telefono": "600111222", "direccion": "Calle Falsa 123"})
    assert r.status_code == 200
    assert "Nombre Actualizado".encode("utf-8") in r.data
    assert b"600111222" in r.data

    r2 = cli.post(f"/tienda/{emp}/cuenta/salir")
    assert r2.status_code in (301, 302)
    r3 = cli.get(f"/tienda/{emp}/cuenta")
    assert r3.status_code in (301, 302)  # sesión cerrada -> vuelve a redirigir a /entrar


def test_webauthn_endpoints_sin_sesion_dan_401(emp, db):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/cuenta/webauthn/registro/iniciar")
    assert r.status_code == 401
    assert r.get_json()["ok"] is False


def _sesion_cliente(cli, emp, enviados, email):
    r1 = cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": email})
    assert r1.status_code == 200
    token = enviados[-1][2].split("?t=", 1)[1].split("\n", 1)[0].strip()
    r2 = cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t={token}")
    assert r2.status_code in (301, 302)


def test_canjear_puntos_tramo_invalido_no_descuenta_saldo(emp, db, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "canjea@test.com")

    r = cli.post(f"/tienda/{emp}/cuenta/canjear", data={"puntos": "37"})
    assert r.status_code == 200
    assert "saldo insuficiente o tramo".encode("utf-8") in r.data


def test_canjear_puntos_con_saldo_suficiente_genera_cupon(emp, db, fab, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "canjea2@test.com")

    from src.db import clientes as cli_db
    cid = cli_db.buscar_cliente_por_codigo("canjea2@test.com", id_empresa=emp)["id"]
    from src.db import fidelizacion as fid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE clientes SET saldo_puntos=100 WHERE id=%s", (cid,))
        conn.commit()

    r = cli.post(f"/tienda/{emp}/cuenta/canjear", data={"puntos": "100"})
    assert r.status_code == 200
    assert "Cupón generado: FID-".encode("utf-8") in r.data
    assert fid.saldo_puntos(cid, id_empresa=emp) == 0

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cupones WHERE id_cliente=%s", (cid,))
        conn.commit()


def test_tickets_sin_compras_muestra_vacio(emp, db, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "sincompras@test.com")

    r = cli.get(f"/tienda/{emp}/cuenta/tickets")
    assert r.status_code == 200
    assert "Todavía no tienes compras".encode("utf-8") in r.data


def test_tickets_lista_y_descarga_pdf_de_compra_propia(emp, db, fab, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "tickets@test.com")

    from src.db import clientes as cli_db
    cid = cli_db.buscar_cliente_por_codigo("tickets@test.com", id_empresa=emp)["id"]
    cod = fab.articulo(id_empresa=emp, precio=10.0, stock_total=5)
    from src.db import conexion
    vid = conexion.registrar_venta_con_items(
        [{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 10.0}],
        cliente={"id": cid}, id_empresa=emp)

    def _limpia_venta():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
            cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
            conn.commit()
    fab.al_limpiar(_limpia_venta)

    r = cli.get(f"/tienda/{emp}/cuenta/tickets")
    assert r.status_code == 200
    assert f"/tienda/{emp}/cuenta/tickets/{vid}.pdf".encode("utf-8") in r.data

    r2 = cli.get(f"/tienda/{emp}/cuenta/tickets/{vid}.pdf")
    assert r2.status_code == 200
    assert r2.mimetype == "application/pdf"


def test_ticket_pdf_de_otro_cliente_da_404(emp, db, fab, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    _sesion_cliente(cli, emp, enviados, "intruso@test.com")

    r = cli.get(f"/tienda/{emp}/cuenta/tickets/999999999.pdf")
    assert r.status_code == 404


def test_webauthn_login_iniciar_cliente_inexistente(emp, db):
    cli = _client()
    r = cli.post(f"/tienda/{emp}/cuenta/webauthn/login/iniciar", json={"email": "nadie@test.com"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


def test_tarjeta_qr_sin_sesion_da_401(emp, db):
    cli = _client()
    r = cli.get(f"/tienda/{emp}/cuenta/tarjeta.png")
    assert r.status_code == 401


def test_cuenta_muestra_tarjeta_con_qr_y_puntos(emp, db, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    cli = _client()
    cli.post(f"/tienda/{emp}/cuenta/entrar", data={"email": "tarjeta@test.com"})
    cuerpo = enviados[0][2]
    token = cuerpo.split("?t=", 1)[1].split("\n", 1)[0].strip()
    cli.get(f"/tienda/{emp}/cuenta/entrar/confirmar?t={token}")

    r = cli.get(f"/tienda/{emp}/cuenta")
    assert r.status_code == 200
    assert f"/tienda/{emp}/cuenta/tarjeta.png".encode("utf-8") in r.data
    assert b"0 " in r.data or b">0<" in r.data or "puntos".encode("utf-8") in r.data

    r2 = cli.get(f"/tienda/{emp}/cuenta/tarjeta.png")
    assert r2.status_code == 200
    assert r2.mimetype == "image/png"
    assert r2.data[:8] == b"\x89PNG\r\n\x1a\n"
