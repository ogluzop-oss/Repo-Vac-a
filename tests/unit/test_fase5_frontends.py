"""
Tests Fase V · Bloques 1-3: Mobile Platform, Web Portal, API Pública.

Verifica: las INTERFACES (mobile/portal) consumen REST/servicios y NUNCA SQL/src.db; scopes por
tipo de portal; OAuth2 client-credentials + scopes de la API pública; y AISLAMIENTO multiempresa
en las apps de desarrollador.
"""

import inspect

import pytest

EMP = "T-F5-A"
EMP_B = "T-F5-B"


# ── Mobile ──────────────────────────────────────────────────────────────────
def test_mobile_descriptor_y_offline():
    from src.services import mobile
    d = mobile.descriptor()
    assert d["comunicacion"] == "rest"            # SIEMPRE REST, nunca SQL
    assert "login" in d["capacidades"] and "pedidos" in d["capacidades"]
    assert set(d["capas"]) >= {"core", "networking", "auth", "sync", "push", "sesion"}
    # Offline-first: outbox + resolución de conflictos.
    ob = mobile.sync.Outbox()
    ob.encolar("pedidos", "crear", {"x": 1})
    assert len(ob.pendientes()) == 1
    ganador = mobile.sync.resolver_conflicto({"version": 2, "v": "L"}, {"version": 1, "v": "R"})
    assert ganador["v"] == "L"


def test_mobile_es_interfaz_sin_sql():
    """La capa móvil (interfaz) consume la REST API; nunca SQL ni src.db."""
    from src.services.mobile import networking, sync, sesion
    for modulo in (networking, sync, sesion):
        codigo = "\n".join(l for l in inspect.getsource(modulo).splitlines()
                           if not l.lstrip().startswith("#"))
        assert "from src.db" not in codigo and "import src.db" not in codigo
        for sql in ("SELECT ", "INSERT ", "UPDATE ", "obtener_conexion"):
            assert sql not in codigo


def test_mobile_cliente_habla_rest():
    from src.services import mobile
    cli = mobile.ClienteMovil()
    # Consume la REST API oficial (test-client en proceso).
    assert cli._cli is not None and cli.base_url == "/api/v1"


# ── Portal ──────────────────────────────────────────────────────────────────
def test_portal_scopes_por_tipo():
    from src.services import portal
    assert set(portal.TIPOS) == {"cliente", "proveedor", "transportista", "empleado",
                                 "asesoria", "auditor"}
    assert portal.acceso.puede("cliente", "pedidos")
    assert not portal.acceso.puede("transportista", "facturas")   # mínimo privilegio
    assert portal.acceso.puede("empleado", "login")               # login siempre
    s = portal.SesionPortal("cliente")
    assert "pedidos" in s.menu() and "firma" in s.menu()


def test_portal_es_interfaz_sin_sql():
    from src.services.portal import portales, acceso, sesion_portal
    for modulo in (portales, acceso, sesion_portal):
        codigo = "\n".join(l for l in inspect.getsource(modulo).splitlines()
                           if not l.lstrip().startswith("#"))
        assert "from src.db" not in codigo and "import src.db" not in codigo
        for sql in ("SELECT ", "INSERT ", "obtener_conexion"):
            assert sql not in codigo


# ── API Pública ───────────────────────────────────────────────────────────────
@pytest.fixture
def limpio(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM api_dev_apps WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            conn.commit()
    _b(); yield; _b()


def test_api_publica_oauth_y_scopes(limpio):
    from src.services import api_publica as ap
    app = ap.registrar_app("Int A", id_empresa=EMP, scopes=["read:orders", "read:kpis"])
    assert app["ok"] and app["client_id"].startswith("cid_")
    tok = ap.emitir_token(app["client_id"], app["client_secret"], scopes=["read:orders"])
    assert tok and tok["token_type"] == "Bearer"
    # Scope concedido → True; no concedido → False.
    assert ap.verificar_scope(tok["access_token"], "read:orders") is True
    assert ap.verificar_scope(tok["access_token"], "write:orders") is False
    # Credenciales inválidas → sin token.
    assert ap.emitir_token(app["client_id"], "secret-malo") is None


def test_api_publica_aislamiento(limpio):
    from src.services import api_publica as ap
    ap.registrar_app("App A", id_empresa=EMP, scopes=["read:orders"])
    ap.registrar_app("App B", id_empresa=EMP_B, scopes=["read:orders"])
    nombres_a = {a["nombre"] for a in ap.listar_apps(EMP)}
    nombres_b = {a["nombre"] for a in ap.listar_apps(EMP_B)}
    assert "App A" in nombres_a and "App B" not in nombres_a     # 0 cruces entre empresas
    assert "App B" in nombres_b and "App A" not in nombres_b


def test_api_publica_sdks_desde_openapi():
    from src.services import api_publica as ap
    assert set(ap.sdks.lenguajes()) == {"python", "javascript", "typescript", "csharp",
                                        "java", "php"}
    assert ap.sdks.descriptor()["fuente"] == "openapi"        # fuente única, sin duplicar la API
    assert isinstance(ap.openapi_publica.documento(), dict)
