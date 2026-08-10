"""
Tests Fase VI · Bloque 11: Cloud Distributed Architecture.

Verifica: Node Registry (registro/estados/heartbeat), Service Discovery distribuido, Load Balancing
(RR/LeastConn/RegionFirst/Sticky), Failover preparado, Cluster health y Storage abstraction. Todo en
memoria (preparación, sin red).
"""

import pytest

from src.platform import cloud


@pytest.fixture(autouse=True)
def _limpio():
    cloud.nodes.limpiar(); cloud.cluster.limpiar(); cloud.routing.reset()
    yield
    cloud.nodes.limpiar(); cloud.cluster.limpiar(); cloud.routing.reset()


def test_node_registry_y_estados():
    assert cloud.nodes.registrar("n1", region="eu", estado=cloud.nodes.READY)
    assert not cloud.nodes.registrar("mal", estado="inexistente")
    cloud.nodes.actualizar("n1", estado=cloud.nodes.MAINTENANCE, carga=0.5)
    assert cloud.nodes.obtener("n1").estado == cloud.nodes.MAINTENANCE
    assert cloud.nodes.obtener("n1") not in cloud.nodes.disponibles()   # mantenimiento no atiende


def test_load_balancing():
    cloud.nodes.registrar("a", region="eu", latencia_ms=10, carga=0.2)
    cloud.nodes.registrar("b", region="eu", latencia_ms=30, carga=0.8)
    cloud.nodes.registrar("c", region="am", latencia_ms=5, carga=0.1)
    # Round Robin rota.
    r1 = cloud.routing.elegir(cloud.routing.ROUND_ROBIN).nombre
    r2 = cloud.routing.elegir(cloud.routing.ROUND_ROBIN).nombre
    assert r1 != r2
    # Least Connections → menor carga/latencia.
    assert cloud.routing.elegir(cloud.routing.LEAST_CONNECTIONS).nombre == "c"
    # Region First → prioriza la región pedida.
    assert cloud.routing.elegir(cloud.routing.REGION_FIRST, region="am").nombre == "c"
    # Sticky → misma sesión, mismo nodo.
    s1 = cloud.routing.elegir(cloud.routing.STICKY, clave_sesion="sess-1").nombre
    s2 = cloud.routing.elegir(cloud.routing.STICKY, clave_sesion="sess-1").nombre
    assert s1 == s2


def test_failover_preparado():
    cloud.nodes.registrar("p", region="eu"); cloud.nodes.registrar("s", region="eu")
    cloud.failover.asignar_rol("g", cloud.failover.PRIMARY, "p")
    cloud.failover.asignar_rol("g", cloud.failover.SECONDARY, "s")
    # Primario vivo → no conmuta.
    assert cloud.failover.plan_conmutacion("g")["conmutar"] is False
    # Primario en mantenimiento → plan de conmutación al secundario (sin ejecutar).
    cloud.nodes.actualizar("p", estado=cloud.nodes.MAINTENANCE)
    plan = cloud.failover.plan_conmutacion("g")
    assert plan["conmutar"] and plan["relevo"] == "s" and plan["ejecutado"] is False


def test_cluster_y_discovery():
    cloud.nodes.registrar("n-eu", region="eu"); cloud.nodes.registrar("n-am", region="am")
    cloud.cluster.crear_cluster("c1", region="eu"); cloud.cluster.asignar_nodo("c1", "n-eu")
    assert cloud.cluster.salud_cluster("c1")["estado"] == "ok"
    topo = cloud.discovery.topologia()
    assert set(topo["regiones"].keys()) == {"eu", "am"}


def test_storage_abstraction():
    assert set(cloud.storage.PROVEEDORES) == {"local", "s3", "azure_blob", "gcs", "minio"}
    st = cloud.storage.proveedor("s3")      # cloud PREPARADO → degrada a local
    assert st.put("t/f6.txt", b"data")
    assert st.get("t/f6.txt") == b"data" and st.exists("t/f6.txt")
    st.delete("t/f6.txt")
    assert not st.exists("t/f6.txt")


def test_registrada_en_plataforma():
    from src import platform as plat
    plat.registry.limpiar()
    plat.bootstrap()
    for esperado in ("cloud", "observability_cloud", "saas_global"):
        assert esperado in plat.registry.nombres()
    plat.registry.limpiar()
