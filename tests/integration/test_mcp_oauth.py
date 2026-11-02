"""Integración · MCP (Model Context Protocol) — OAuth 2.1 + PKCE + protocolo JSON-RPC básico.

Regresión PERMANENTE del conector MCP de SOMA (`src/mcp_server/{transport,oauth}.py`), construida
contra el backend Flask REAL (`src.backend.app.crear_app().test_client()`, mismo patrón que
`tests/integration/test_api_auth.py`/`test_api_recursos.py`) y datos reales (`fab`). Cubre:

  1. Flujo OAuth 2.1 + PKCE completo: DCR -> /authorize (login real) -> /token -> JWT real válido.
  2. Casos negativos de PKCE/OAuth 2.1 (verifier incorrecto, redirect_uri distinto, código
     reutilizado, code_challenge ausente).
  3. Refresh token grant + revocación (RFC 7009).
  4. Fundamentos del endpoint `/mcp`: `initialize` (serverInfo), `tools/list` (8 tools), 401 sin
     bearer token.

Las 7 tools en sí (lectura+escritura), el aislamiento multiempresa y la gobernanza se cubren en
`test_mcp_tools.py` (archivo hermano).
"""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.db

REDIRECT_URI = "https://chat.test.example/callback"


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


# ── Helpers OAuth/PKCE (reutilizados también, en espíritu, por test_mcp_tools.py) ───────────────
def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _borrar_app(db, client_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM api_dev_apps WHERE client_id=%s", (client_id,))
        conn.commit()


def _borrar_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()


def _borrar_codigos_mcp(db, client_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mcp_oauth_codes WHERE client_id=%s", (client_id,))
        conn.commit()


def _registrar_cliente(db, fab, cliente, redirect_uri=REDIRECT_URI, nombre="Cliente MCP Test"):
    r = cliente.post("/mcp/oauth/register", json={"client_name": nombre, "redirect_uris": [redirect_uri]})
    assert r.status_code == 201, r.get_data(as_text=True)
    app = r.get_json()
    fab.al_limpiar(lambda: _borrar_app(db, app["client_id"]))
    fab.al_limpiar(lambda: _borrar_codigos_mcp(db, app["client_id"]))
    return app


def _autorizar(cliente, app, *, usuario, password, challenge, id_empresa=None, state="estado1",
               redirect_uri=None, client_id=None):
    data = {
        "response_type": "code",
        "client_id": client_id or app["client_id"],
        "redirect_uri": redirect_uri or app["redirect_uris"][0],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp",
        "usuario": usuario,
        "password": password,
    }
    if id_empresa:
        data["id_empresa"] = id_empresa
    return cliente.post("/mcp/oauth/authorize", data=data)


def _code_de_redirect(resp):
    assert resp.status_code == 302, resp.get_data(as_text=True)
    loc = resp.headers["Location"]
    qs = parse_qs(urlparse(loc).query)
    return qs.get("code", [None])[0], qs.get("state", [None])[0]


def _canjear(cliente, app, *, code, verifier, redirect_uri=None, client_id=None, client_secret=None):
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id or app["client_id"],
        "client_secret": client_secret if client_secret is not None else app["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri or app["redirect_uris"][0],
        "code_verifier": verifier,
    }
    return cliente.post("/mcp/oauth/token", data=data)


def _flujo_completo(db, fab, cliente, *, usuario, password, id_empresa=None,
                    redirect_uri=REDIRECT_URI):
    """DCR -> authorize -> token. Devuelve (app, verifier, body_token) con un access/refresh REAL."""
    app = _registrar_cliente(db, fab, cliente, redirect_uri=redirect_uri)
    verifier, challenge = _pkce()
    resp = _autorizar(cliente, app, usuario=usuario, password=password, id_empresa=id_empresa,
                      challenge=challenge)
    code, _ = _code_de_redirect(resp)
    r = _canjear(cliente, app, code=code, verifier=verifier, redirect_uri=redirect_uri)
    assert r.status_code == 200, r.get_data(as_text=True)
    return app, verifier, r.get_json()


def _usuario_mcp(fab, db, nombre, **kw):
    u = fab.usuario(nombre=nombre, password="Clave_Mcp_123456", perfil=kw.pop("perfil", "ADMINISTRADOR"), **kw)
    fab.al_limpiar(lambda: _borrar_sesiones(db, u["id"]))
    return u


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Flujo OAuth 2.1 + PKCE completo (DCR -> authorize -> token -> JWT real)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFlujoOAuthCompleto:
    def test_dcr_registra_app_real(self, db, fab, cliente):
        app = _registrar_cliente(db, fab, cliente)
        assert app["client_id"].startswith("cid_")
        assert app["client_secret"].startswith("csec_")
        assert app["grant_types"] == ["authorization_code", "refresh_token"]
        # El client quedó realmente persistido en api_dev_apps (no solo en la respuesta HTTP).
        from src.services.api_publica import developer
        fila = developer.obtener_app(app["client_id"])
        assert fila and fila["estado"] == "activa" and fila["redirect_uri"] == REDIRECT_URI

    def test_authorize_rechaza_credenciales_invalidas(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_OAUTH_BADPW")
        app = _registrar_cliente(db, fab, cliente)
        _, challenge = _pkce()
        resp = _autorizar(cliente, app, usuario=u["nombre"], password="mala-contrasena",
                          challenge=challenge)
        assert resp.status_code == 401
        assert "Credenciales incorrectas" in resp.get_data(as_text=True)

    def test_flujo_completo_emite_jwt_real_y_valido(self, db, fab, cliente):
        """DCR -> authorize (login real) -> token -> el access_token es un JWT real que
        `seguridad.tokens.verificar` acepta, con el `sub`/`empresa`/`rol` del usuario real."""
        u = _usuario_mcp(fab, db, "MCP_OAUTH_OK", perfil="ADMINISTRADOR")
        app, verifier, body = _flujo_completo(db, fab, cliente, usuario=u["nombre"],
                                              password="Clave_Mcp_123456")
        assert body["token_type"] == "Bearer"
        assert body["access_token"] and body["refresh_token"]
        assert body["scope"] == "mcp"

        from src.seguridad import tokens
        claims = tokens.verificar(body["access_token"], "access")
        assert claims is not None
        assert claims["sub"] == str(u["id"])
        assert claims["empresa"] == fab.EMP_DEFECTO
        assert claims["rol"] == "ADMINISTRADOR"
        assert claims["amr"] == ["pwd"]   # sin 2º factor activo en este usuario de prueba

        # El access token real funciona contra /mcp (whoami) — cierre del círculo DCR->tools/call.
        r = cliente.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "whoami", "arguments": {}}},
                         headers={"Authorization": f"Bearer {body['access_token']}"})
        assert r.status_code == 200
        import json as _json
        contenido = _json.loads(r.get_json()["result"]["content"][0]["text"])
        assert contenido["id_usuario"] == str(u["id"])
        assert contenido["id_empresa"] == fab.EMP_DEFECTO

    def test_authorize_scoped_a_empresa_explicita(self, db, fab, cliente):
        """El campo opcional `id_empresa` del formulario de login resuelve el tenant igual que en
        el login REST (`/auth/login`): el JWT final lleva la empresa indicada."""
        emp_b = fab.empresa("EMP MCP OAUTH B")
        u = _usuario_mcp(fab, db, "MCP_OAUTH_EMPB", id_empresa=emp_b)
        _, _, body = _flujo_completo(db, fab, cliente, usuario=u["nombre"],
                                     password="Clave_Mcp_123456", id_empresa=emp_b)
        from src.seguridad import tokens
        claims = tokens.verificar(body["access_token"], "access")
        assert claims["empresa"] == emp_b


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Casos negativos PKCE / OAuth 2.1 (línea base de seguridad del conector)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPKCENegativo:
    def test_code_verifier_incorrecto_rechazado(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_PKCE_BADVER")
        app = _registrar_cliente(db, fab, cliente)
        verifier, challenge = _pkce()
        resp = _autorizar(cliente, app, usuario=u["nombre"], password="Clave_Mcp_123456",
                          challenge=challenge)
        code, _ = _code_de_redirect(resp)
        otro_verifier, _ = _pkce()
        r = _canjear(cliente, app, code=code, verifier=otro_verifier)
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_grant"
        assert "PKCE" in r.get_json()["error_description"]

    def test_redirect_uri_distinto_en_token_rechazado(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_PKCE_BADURI")
        app = _registrar_cliente(db, fab, cliente)
        verifier, challenge = _pkce()
        resp = _autorizar(cliente, app, usuario=u["nombre"], password="Clave_Mcp_123456",
                          challenge=challenge)
        code, _ = _code_de_redirect(resp)
        # El canje declara un redirect_uri que NO coincide con el usado en /authorize.
        r = _canjear(cliente, app, code=code, verifier=verifier,
                     redirect_uri="https://otro-destino.test/distinto")
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_grant"

    def test_codigo_reutilizado_rechazado(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_PKCE_REPLAY")
        app = _registrar_cliente(db, fab, cliente)
        verifier, challenge = _pkce()
        resp = _autorizar(cliente, app, usuario=u["nombre"], password="Clave_Mcp_123456",
                          challenge=challenge)
        code, _ = _code_de_redirect(resp)
        r1 = _canjear(cliente, app, code=code, verifier=verifier)
        assert r1.status_code == 200
        # Segundo canje del MISMO código (p. ej. interceptado) — debe rechazarse SIEMPRE,
        # incluso con el verifier correcto.
        r2 = _canjear(cliente, app, code=code, verifier=verifier)
        assert r2.status_code == 400
        assert r2.get_json()["error"] == "invalid_grant"

    def test_code_challenge_ausente_en_authorize_rechazado(self, db, fab, cliente):
        """OAuth 2.1: PKCE es OBLIGATORIO. `/authorize` sin `code_challenge` se rechaza antes de
        siquiera mostrar el login (no hace falta credenciales reales para este caso)."""
        app = _registrar_cliente(db, fab, cliente)
        r = cliente.get("/mcp/oauth/authorize", query_string={
            "response_type": "code", "client_id": app["client_id"],
            "redirect_uri": app["redirect_uris"][0], "state": "x",
        })
        assert r.status_code == 400
        assert r.get_json()["error"] == "invalid_request"
        assert "code_challenge" in r.get_json()["error_description"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Refresh token grant + revocación (RFC 7009)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRefreshYRevocacion:
    def test_refresh_emite_access_nuevo(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_REFRESH_OK")
        _, _, body = _flujo_completo(db, fab, cliente, usuario=u["nombre"],
                                     password="Clave_Mcp_123456")
        r = cliente.post("/mcp/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": body["refresh_token"],
        })
        assert r.status_code == 200
        nuevo = r.get_json()["access_token"]
        assert nuevo and nuevo != body["access_token"]
        from src.seguridad import tokens
        claims = tokens.verificar(nuevo, "access")
        assert claims and claims["sub"] == str(u["id"])

    def test_revoke_invalida_refresh_para_futuros_refresh(self, db, fab, cliente):
        u = _usuario_mcp(fab, db, "MCP_REVOKE_OK")
        _, _, body = _flujo_completo(db, fab, cliente, usuario=u["nombre"],
                                     password="Clave_Mcp_123456")
        rr = cliente.post("/mcp/oauth/revoke", data={"token": body["refresh_token"]})
        assert rr.status_code == 200
        # Tras revocar, el MISMO refresh token ya no debe servir para refrescar.
        r2 = cliente.post("/mcp/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": body["refresh_token"],
        })
        assert r2.status_code == 400
        assert r2.get_json()["error"] == "invalid_grant"

    def test_revoke_de_token_desconocido_no_revela_nada(self, cliente):
        # RFC 7009: responder 200 siempre, exista o no el token.
        r = cliente.post("/mcp/oauth/revoke", data={"token": "no-existe-este-token"})
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Fundamentos del endpoint /mcp (handshake, listado de tools, auth)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestProtocoloMCPBasico:
    def _token(self, db, fab, cliente, nombre="MCP_PROTO_BASE"):
        u = _usuario_mcp(fab, db, nombre)
        _, _, body = _flujo_completo(db, fab, cliente, usuario=u["nombre"],
                                     password="Clave_Mcp_123456")
        return body["access_token"]

    def test_initialize_identifica_al_servidor(self, db, fab, cliente):
        tok = self._token(db, fab, cliente)
        r = cliente.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        j = r.get_json()
        assert j["result"]["serverInfo"]["name"] == "SOMA — Smart Manager Copilot"

    def test_tools_list_devuelve_las_8_tools_registradas(self, db, fab, cliente):
        tok = self._token(db, fab, cliente, nombre="MCP_PROTO_LIST")
        r = cliente.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                         headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        nombres = {t["name"] for t in r.get_json()["result"]["tools"]}
        assert nombres == {
            "whoami", "consultar_stock", "consultar_movimientos_stock",
            "consultar_alertas_reposicion", "resumen_ventas", "estado_rfid",
            "crear_borrador_pedido_compra", "gestionar_articulo_catalogo",
        }

    def test_sin_bearer_token_rechazado(self, cliente):
        r = cliente.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        assert r.status_code == 401
        assert r.get_json()["error"] == "unauthorized"

    def test_bearer_token_invalido_rechazado(self, cliente):
        r = cliente.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
                         headers={"Authorization": "Bearer esto-no-es-un-jwt-valido"})
        assert r.status_code == 401
