"""
Tests PCD · Fase 1 (RFC-CD-006): fachada de capacidades + scaffolding de servicios + registro de
contratos en el Service Registry + REST/GraphQL cableados.

Verifica: servicios DESCUBRIBLES; dependencia SOLO por capacidades; resolvers sin SQL; REST/GraphQL
delegan en el servicio; y que NO hay lógica de negocio todavía (solo scaffolding).
"""

import inspect

from src import platform as plat


def test_capabilities_facade():
    from src.platform import capabilities as cap
    # La fachada expone las capacidades Enterprise que la PCD necesita.
    for c in ("eventbus", "workflow", "rules", "scheduler", "ccp", "ia", "observabilidad",
              "marketplace", "saas_global", "storage"):
        assert c in cap.capacidades()
    # Degradable: capacidades reales disponibles en este entorno.
    assert cap.disponible("eventbus") and cap.disponible("marketplace")
    assert cap.obtener("no_existe") is None


def test_pcd_declara_contratos_y_plataforma_registra():
    plat.registry.limpiar()
    plat.bootstrap()
    nombres = plat.registry.nombres()
    # La PCD DECLARA; la plataforma REGISTRA (aislamiento del registry).
    for s in ("comercio_digital", "cd_transacciones", "cd_inventario", "cd_publicaciones",
              "cd_canales", "cd_presencia", "cd_sync", "cd_checkout"):
        assert s in nombres, f"{s} no registrado"
    # Descubrible por capacidad y con dependencias hacia la infra existente.
    assert "cd_transacciones" in [c.nombre for c in plat.discovery.por_capacidad("transacciones")]
    assert plat.discovery.resolver_dependencias("cd_transacciones").get("workflow") is True
    plat.registry.limpiar()


def test_descriptor_estructura():
    from src.services import comercio_digital as cd
    d = cd.descriptor()
    assert d["plataforma"] == "Comercio Digital" and d["estado"] in ("scaffolding", "en_progreso",
                                                                     "operativo")
    assert set(d["subservicios"]) >= {"cd_transacciones", "cd_inventario", "cd_canales"}
    # El motor de inventario declara la separación Availability/Fulfillment (CD-005).
    inv = d["subservicios"]["cd_inventario"]
    assert "availability" in inv["motores"] and "fulfillment" in inv["motores"]
    assert inv["motores"]["fulfillment"]["mueve_stock"] is False


def test_pcd_depende_solo_de_capacidades_para_motores():
    """La PCD reutiliza los MOTORES solo por `platform.capabilities`, nunca importándolos directo.
    (Un servicio de dominio SÍ puede acceder a su propia BD: eso es la capa de dominio, no un motor.)"""
    from src.services import comercio_digital
    from src.services.comercio_digital import transacciones, inventario, canales
    for modulo in (comercio_digital, transacciones, inventario, canales):
        codigo = "\n".join(l for l in inspect.getsource(modulo).splitlines()
                           if not l.lstrip().startswith("#") and '"""' not in l)
        for prohibido in ("from src.services.workflow", "from src.services.rules import",
                          "from src.services import ccp", "from src.services import rules",
                          "from src.services import scheduler", "from src.services import marketplace"):
            assert prohibido not in codigo, f"{modulo.__name__} acopla a un motor: {prohibido}"


def test_graphql_commerce_resuelve_via_servicio():
    from src.api.graphql import schema
    esq = schema.esquema()
    assert "commerce" in esq["queries"]
    assert esq["queries"]["commerce"]["servicio"] == "comercio_digital.descriptor"
    r = schema.ejecutar("commerce", {}, contexto={"id_empresa": "T-CD-A",
                                                  "usuario": {"perfil": "ADMINISTRADOR"}})
    assert "data" in r and r["data"]["commerce"]["plataforma"] == "Comercio Digital"
    # Sin tenant → no autorizado.
    assert "errors" in schema.ejecutar("commerce", {}, contexto={})


def test_graphql_resolver_commerce_sin_sql():
    from src.api.graphql import queries
    src = inspect.getsource(queries._q_commerce)
    assert "from src.db" not in src and "SELECT " not in src and "obtener_conexion" not in src


def test_rest_commerce_router_registrado():
    from src.api.routers import ROUTERS
    import src.api.routers.commerce as commerce
    assert commerce in ROUTERS
    # El router delega en el servicio (sin SQL).
    src = inspect.getsource(commerce)
    assert "comercio_digital" in src and "from src.db" not in src and "SELECT " not in src
