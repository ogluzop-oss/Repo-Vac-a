"""
Autenticación passwordless del cliente final (Generador de Apps Móviles PWA, Fase 2): Magic Link +
sesión DB-backed. BD real (`*_test`); envío de correo mockeado con el MISMO patrón ya usado en
`test_carrito_abandono.py` (nunca toca SMTP real)."""

import pytest

from src.db import clientes as cli_db
from src.db import clientes_sesiones as ses_db
from src.services.comercio_digital import clientes_auth as auth

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.empresa("CLIENTES AUTH TEST")


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_clientes_sesiones WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM mfa_webauthn_credenciales WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM clientes WHERE id_empresa=%s", (emp,))
        conn.commit()


def _mockear_envio(monkeypatch, enviados):
    monkeypatch.setattr("src.db.correo.listar_correos",
                        lambda eid: [{"id_correo": "buzon-fake", "estado": "activo"}])
    monkeypatch.setattr(
        "src.services.correo.servicio.enviar_documento",
        lambda id_correo, dest, asunto, cuerpo="", adjuntos=None:
            (enviados.append((dest, asunto, cuerpo)) or (True, "ok")))


# ── Magic Link ─────────────────────────────────────────────────────────────
def test_solicitar_magic_link_sin_buzon_activo_degrada_honesto(db, emp):
    r = auth.solicitar_magic_link(emp, "comprador@test.com")
    assert r["ok"] is False and r["motivo"] == "sin_buzon_activo"


def test_solicitar_magic_link_email_invalido(db, emp):
    r = auth.solicitar_magic_link(emp, "no-es-un-email")
    assert r["ok"] is False and r["motivo"] == "email_invalido"


def test_solicitar_magic_link_autocrea_cliente_y_envia(db, emp, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    r = auth.solicitar_magic_link(emp, "nuevo@test.com", base_url="http://localhost:8090")
    assert r["ok"] is True
    assert len(enviados) == 1
    dest, asunto, cuerpo = enviados[0]
    assert dest == "nuevo@test.com"
    assert "http://localhost:8090/tienda/" in cuerpo and "/cuenta/entrar/confirmar?t=" in cuerpo
    # El cliente queda registrado de verdad (misma tabla que usa el TPV).
    encontrados = cli_db.buscar_clientes("nuevo@test.com", id_empresa=emp)
    assert len(encontrados) == 1 and encontrados[0]["email"] == "nuevo@test.com"


def test_solicitar_magic_link_reutiliza_cliente_existente(db, emp, monkeypatch):
    cid = cli_db.crear_cliente("Cliente Ya Existente", email="existente@test.com", id_empresa=emp)
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    auth.solicitar_magic_link(emp, "existente@test.com")
    assert len(cli_db.buscar_clientes("existente@test.com", id_empresa=emp)) == 1  # no duplica


def test_confirmar_magic_link_token_invalido(db, emp):
    r = auth.confirmar_magic_link("esto-no-es-un-token-valido")
    assert r["ok"] is False and r["motivo"] == "enlace_invalido_o_caducado"


def test_flujo_completo_magic_link_abre_sesion_real(db, emp, monkeypatch):
    enviados = []
    _mockear_envio(monkeypatch, enviados)
    auth.solicitar_magic_link(emp, "flujo@test.com")
    cuerpo = enviados[0][2]
    token = cuerpo.split("?t=", 1)[1].split("\n", 1)[0].strip()

    r = auth.confirmar_magic_link(token)
    assert r["ok"] is True
    assert r["cliente"]["email"] == "flujo@test.com"
    assert r["id_empresa"] == emp

    # La sesión queda persistida de verdad y es resoluble.
    cliente_sesion = auth.sesion_actual(r["token_sesion"])
    assert cliente_sesion is not None and cliente_sesion["email"] == "flujo@test.com"


def test_confirmar_magic_link_caducado(db, emp, monkeypatch):
    from src.services.seguridad.mfa_webauthn import _firmar_reto
    cid = cli_db.crear_cliente("Cliente Caducado", email="caducado@test.com", id_empresa=emp)
    token_ya_caducado = _firmar_reto(f"{emp}|{cid}".encode(), ttl=-1)
    r = auth.confirmar_magic_link(token_ya_caducado)
    assert r["ok"] is False and r["motivo"] == "enlace_invalido_o_caducado"


def test_confirmar_magic_link_aisla_por_empresa(db, emp, fab):
    """Un token firmado para OTRA empresa nunca debe resolver un cliente de esta."""
    from src.services.seguridad.mfa_webauthn import _firmar_reto
    otra_emp = fab.empresa("OTRA EMPRESA AUTH TEST")
    cid = cli_db.crear_cliente("Cliente De Otra Empresa", email="otra@test.com", id_empresa=otra_emp)
    # Token que dice pertenecer a `emp` pero el cliente real es de `otra_emp`.
    token_falseado = _firmar_reto(f"{emp}|{cid}".encode())
    r = auth.confirmar_magic_link(token_falseado)
    assert r["ok"] is False
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id_empresa=%s", (otra_emp,))
        conn.commit()


# ── Sesión ───────────────────────────────────────────────────────────────────
def test_sesion_actual_token_inexistente(db, emp):
    assert auth.sesion_actual("token-que-no-existe") is None


def test_cerrar_sesion(db, emp):
    cid = cli_db.crear_cliente("Cliente Sesion", email="sesion@test.com", id_empresa=emp)
    token = ses_db.crear_sesion(emp, cid)
    assert auth.sesion_actual(token) is not None
    assert auth.cerrar_sesion(token) is True
    assert auth.sesion_actual(token) is None


# ── WebAuthn (sin librería instalada -> degrada honesto, no crashea) ─────────
def test_webauthn_iniciar_registro_cliente_inexistente(db, emp):
    r = auth.webauthn_iniciar_registro(emp, 999999)
    assert r["ok"] is False and r["motivo"] == "cliente_no_encontrado"


def test_webauthn_iniciar_login_cliente_inexistente(db, emp):
    r = auth.webauthn_iniciar_login(emp, "no-existe@test.com")
    assert r["ok"] is False and r["motivo"] == "cliente_no_encontrado"


def test_webauthn_prefijo_evita_colision_con_empleados(db, emp):
    """El id_usuario de un cliente en mfa_webauthn_credenciales nunca puede coincidir con el de un
    empleado (prefijo `cli:`), aunque compartan el mismo id numérico."""
    assert auth._prefijo_webauthn(5) == "cli:5"
    assert auth._prefijo_webauthn(5) != "5"
