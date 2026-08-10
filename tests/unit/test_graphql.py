"""
Tests de la GraphQL Enterprise Layer (Fase IV · Bloque 1).

Verifica: (1) la capa resuelve EXCLUSIVAMENTE mediante servicios (0 SQL / 0 src.db en los resolvers);
(2) toda operación declara su servicio de destino; (3) auth/tenant obligatorios; (4) aislamiento
multiempresa (el resolver recibe el tenant del contexto); (5) SDL/esquema construibles.
"""

import inspect

from src.api.graphql import mutations, queries, schema


def test_esquema_y_sdl():
    esq = schema.esquema()
    assert esq["queries"] and esq["mutations"]
    # Toda query/mutation declara su servicio de destino (garantía de no acceso directo a BD).
    assert all(m["servicio"] for m in esq["queries"].values())
    assert all(m["servicio"] for m in esq["mutations"].values())
    sdl = schema.sdl()
    assert "type Query {" in sdl and "type Mutation {" in sdl and "type Subscription {" in sdl


def test_resolvers_sin_sql_ni_bd():
    """Los resolvers NUNCA contienen SQL ni importan src.db: GraphQL→Servicios→Dominio→BD."""
    for modulo in (queries, mutations):
        # Solo las líneas de CÓDIGO (se ignoran docstrings/comentarios que mencionen la regla).
        codigo = "\n".join(l for l in inspect.getsource(modulo).splitlines()
                           if not l.lstrip().startswith("#"))
        assert "from src.db" not in codigo, f"{modulo.__name__} importa src.db"
        assert "import src.db" not in codigo, f"{modulo.__name__} importa src.db"
        for sql in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "obtener_conexion", "cursor("):
            assert sql not in codigo, f"{modulo.__name__} contiene SQL: {sql}"


def test_auth_tenant_obligatorio():
    # Sin tenant → error de autorización.
    r = schema.ejecutar("communications", {"limite": 5}, contexto={})
    assert "errors" in r and r["errors"][0]["codigo"] == "unauthorized"
    # Con tenant → data.
    ctx = {"id_empresa": "T-GQL-A", "usuario": {"perfil": "ADMINISTRADOR"}}
    r2 = schema.ejecutar("communications", {"limite": 5}, contexto=ctx)
    assert "data" in r2 and "communications" in r2["data"]


def test_operacion_desconocida():
    ctx = {"id_empresa": "T-GQL-A", "usuario": {"perfil": "ADMINISTRADOR"}}
    r = schema.ejecutar("no_existe", {}, contexto=ctx)
    assert r["errors"][0]["codigo"] == "unknown_operation"


def test_resuelve_via_servicio_y_aislamiento(monkeypatch):
    """El resolver delega en el servicio ccp y le pasa el tenant del contexto (no de los args)."""
    from src.services import ccp
    capturado = {}

    def _fake(id_empresa=None, limite=50, **_):
        capturado["id_empresa"] = id_empresa
        return [{"com_id": "X", "empresa": id_empresa}]

    monkeypatch.setattr(ccp, "historial_comunicaciones", _fake)
    r = schema.ejecutar("communications", {"limite": 3},
                        contexto={"id_empresa": "EMP-A", "usuario": {"perfil": "ADMINISTRADOR"}})
    assert r["data"]["communications"][0]["empresa"] == "EMP-A"
    assert capturado["id_empresa"] == "EMP-A"     # tenant del contexto, no de los args

    # Otra empresa: el servicio recibe SU tenant (aislamiento estricto).
    schema.ejecutar("communications", {"limite": 3},
                    contexto={"id_empresa": "EMP-B", "usuario": {"perfil": "ADMINISTRADOR"}})
    assert capturado["id_empresa"] == "EMP-B"


def test_subscriptions_preparadas():
    esq = schema.esquema()
    # Subscriptions declaradas y mapeadas a eventos del Corporate Event Bus (sin tiempo real aún).
    assert esq["subscriptions"]
    assert all(s.get("evento") for s in esq["subscriptions"].values())
