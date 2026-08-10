"""
Tests Fase VI · Bloque 13: Global SaaS Platform.

Verifica: regiones + resolución Region→Cluster→Node→Tenant, planes globales, límites por plan/empresa
+ gate de consumo, feature flags cloud jerárquicos, configuración global, modelos de despliegue y
AISLAMIENTO multiempresa/multi-región (0 cruces).
"""

import pytest

EMP = "T-SG-A"
EMP_B = "T-SG-B"


@pytest.fixture
def limpio(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("empresa_region", "saas_limites", "saas_consumo"):
                cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            cur.execute("DELETE FROM cloud_feature_flags WHERE flag LIKE 't_sg_%'")
            conn.commit()
    _b(); yield; _b()


def test_regiones_y_resolucion(limpio):
    from src.services import saas_global as sg
    from src.platform import cloud
    codigos = {r["codigo"] for r in sg.regiones.listar_regiones()}
    assert {"eu", "am", "as", "af", "oc"} <= codigos
    assert sg.regiones.asignar_region(EMP, "am")
    assert sg.regiones.region_de(EMP) == "am"
    cloud.nodes.limpiar(); cloud.nodes.registrar("n-am", region="am")
    res = sg.regiones.resolver(EMP)
    assert res["region"] == "am" and res["nodo"] == "n-am" and res["tenant"] == EMP
    cloud.nodes.limpiar()


def test_planes_y_limites(limpio):
    from src.services import saas_global as sg
    assert set(sg.planes_global.PLANES) == {"starter", "business", "professional", "enterprise",
                                            "corporate", "government"}
    sg.limites.sembrar_desde_plan(EMP, "starter")
    assert sg.limites.limite("usuarios", id_empresa=EMP) == 3
    # Gate de consumo.
    sg.consumo.registrar("usuarios", 2, id_empresa=EMP)
    d = sg.limites.dentro_de_limite("usuarios", id_empresa=EMP)
    assert d["dentro"] and d["restante"] == 1
    sg.consumo.registrar("usuarios", 5, id_empresa=EMP)     # supera el límite
    assert sg.limites.dentro_de_limite("usuarios", id_empresa=EMP)["dentro"] is False


def test_feature_flags_jerarquia(limpio):
    from src.services import saas_global as sg
    sg.feature_flags.fijar("t_sg_flag", False, ambito="global")
    sg.feature_flags.fijar("t_sg_flag", True, ambito="empresa", ambito_id=EMP)
    # La empresa concreta gana sobre el global; otra empresa hereda el global.
    assert sg.feature_flags.activo("t_sg_flag", id_empresa=EMP) is True
    assert sg.feature_flags.activo("t_sg_flag", id_empresa=EMP_B) is False
    # Usuario gana sobre empresa.
    sg.feature_flags.fijar("t_sg_flag", False, ambito="usuario", ambito_id="u1")
    assert sg.feature_flags.activo("t_sg_flag", id_usuario="u1", id_empresa=EMP) is False


def test_aislamiento_multiempresa(limpio):
    from src.services import saas_global as sg
    sg.regiones.asignar_region(EMP, "eu")
    sg.regiones.asignar_region(EMP_B, "am")
    assert sg.regiones.region_de(EMP) == "eu" and sg.regiones.region_de(EMP_B) == "am"
    sg.limites.sembrar_desde_plan(EMP, "enterprise")
    # Los límites de EMP no aplican a EMP_B (que no tiene ninguno propio).
    assert sg.limites.limite("usuarios", id_empresa=EMP) == 250
    assert sg.limites.limite("usuarios", id_empresa=EMP_B) == 0


def test_configuracion_y_deployment():
    from src.services import saas_global as sg
    assert len(sg.configuracion_global.idiomas()) >= 2
    assert sg.configuracion_global.formato_region("eu")["moneda"] == "EUR"
    assert set(sg.deployment.MODOS) == {"cloud", "on_premise", "hybrid", "edge"}
    assert sg.deployment.fijar_modo("hybrid") and sg.deployment.modo_actual() == "hybrid"
    assert sg.deployment.capacidades("edge")["edge"] is True
    sg.deployment.fijar_modo("cloud")
