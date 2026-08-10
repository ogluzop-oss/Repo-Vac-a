"""
Tests de la Preparación para Microservicios (Fase IV · Bloque 3).

Cubre: registro de servicios (contratos), discovery por nombre/capacidad/transporte/ruta, versionado
SemVer + compatibilidad, health checks agregados, heartbeat, routing/gateway (abstracción) y que los
eventos se declaran sobre el Corporate Event Bus (nunca un bus paralelo).
"""

import pytest

from src import platform as plat
from src.platform.contracts import Request, ServiceContract
from src.platform.versioning import Version


@pytest.fixture(autouse=True)
def _limpio():
    plat.registry.limpiar()
    yield
    plat.registry.limpiar()


def test_bootstrap_registra_subsistemas():
    n = plat.bootstrap()
    assert n >= 10
    nombres = plat.registry.nombres()
    for esperado in ("ioc", "ccp", "rest_api", "graphql", "eventbus", "marketplace", "observability"):
        assert esperado in nombres


def test_versionado_semver():
    assert Version.parse("2.3.1") > Version.parse("2.3.0")
    assert Version.parse("2.3.1").compatible_con("2.0.0")        # mismo major, disponible >= requerido
    assert not Version.parse("2.3.1").compatible_con("3.0.0")    # distinto major
    assert not Version.parse("1.9.9").compatible_con("2.0.0")
    assert Version.parse("v1.2.3") == Version(1, 2, 3)


def test_registro_y_discovery():
    plat.bootstrap()
    # Por capacidad.
    assert "ccp" in [c.nombre for c in plat.discovery.por_capacidad("comunicaciones")]
    # Por transporte.
    assert "graphql" in [c.nombre for c in plat.discovery.por_transporte("graphql")]
    # Por ruta.
    assert plat.routing.resolver("/communications").nombre == "ccp"
    # Compatibilidad declarada.
    assert plat.discovery.compatible("ccp", "2.0.0")
    # Dependencias resueltas.
    deps = plat.discovery.resolver_dependencias("graphql")
    assert deps.get("ccp") is True


def test_contrato_invalido_no_se_registra():
    malo = ServiceContract(nombre="", version="1.0.0")
    assert plat.registry.registrar(malo) is False
    malo2 = ServiceContract(nombre="x", transportes=("inexistente",))
    assert plat.registry.registrar(malo2) is False


def test_health_y_heartbeat():
    plat.bootstrap()
    plat.heartbeat.latir("ccp")
    assert plat.heartbeat.esta_vivo("ccp")
    g = plat.health.global_()
    assert g["total"] >= 10 and g["estado"] in ("ok", "degraded", "unknown")
    hs = plat.health.de_servicio("ccp")
    assert hs is not None and hs.version == "2.0.0"


def test_gateway_enruta_sin_ejecutar_por_defecto():
    plat.bootstrap()
    # Sin handler de red: el Gateway confirma el enrutado (preparación), no ejecuta.
    req = Request(operacion="/communications", transporte="rest",
                  auth=plat.contracts.AuthContext(id_empresa="EMP-A"))
    resp = plat.gateway.enrutar(req)
    assert resp.ok and resp.datos["enrutado_a"] == "ccp"


def test_gateway_graphql_resuelve_via_capa():
    plat.bootstrap()
    # El handler integrado de 'graphql' delega en la capa GraphQL (que resuelve vía servicios).
    req = Request(operacion="communications", args={"limite": 3}, transporte="graphql",
                  auth=plat.contracts.AuthContext(id_empresa="EMP-A", perfil="ADMINISTRADOR"))
    resp = plat.gateway.enrutar(req)
    assert resp.ok
    assert "data" in resp.datos or "errors" in resp.datos    # respuesta estilo GraphQL


def test_eventos_sobre_event_bus():
    """Los eventos de plataforma se declaran sobre el Corporate Event Bus, no un bus paralelo."""
    from src.platform.contracts import Event
    e = Event(tipo="ServiceRegistered", id_empresa="EMP-A", ref_entidad="servicio", ref_id="ccp")
    assert e.tipo and e.ts > 0
    # El Event Bus corporativo es la única vía (importable y con catálogo).
    from src.services import eventbus
    assert hasattr(eventbus, "publish") and hasattr(eventbus, "subscribe")
