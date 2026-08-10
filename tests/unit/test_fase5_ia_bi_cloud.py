"""
Tests Fase V · Bloques 5-7: AI Agents Platform, Data Lake + BI, Multi-Tenant Cloud Manager,
y el registro de todos los subsistemas Fase V en la plataforma (preparación microservicios).

Verifica reutilización de la infraestructura existente (agentes/workflow/CCP, bi_corp.dw, saas/
observabilidad), sin motores paralelos, y la integración en el Service Registry.
"""

import pytest

from src import platform as plat


@pytest.fixture(autouse=True)
def _limpio():
    plat.registry.limpiar()
    yield
    plat.registry.limpiar()


# ── AI Agents Platform ─────────────────────────────────────────────────────────
def test_agents_platform():
    from src.services import agents_platform as ap
    assert len(ap.AGENTES) == 12
    for dom in ("compras", "ventas", "rrhh", "fiscal", "inventario", "logistica", "crm", "sat"):
        assert dom in ap.AGENTES
    a = ap.agente("ventas")
    caps = a.capacidades()
    # Capacidades transversales que reutilizan la infraestructura existente.
    assert {"consultar", "iniciar_workflow", "enviar_comunicacion", "solicitar_aprobacion"} <= set(caps)
    assert a.descriptor()["modulo_independiente"] is True
    # El panel agrega los especialistas existentes (no un sistema paralelo).
    assert "agentes" in ap.panel()


def test_agents_reutilizan_especialistas(monkeypatch):
    """`consultar` delega en services.agentes.manager (Especialistas IA), no en lógica nueva."""
    import src.services.agentes as agentes_mod

    class _FakeMgr:
        def delegar(self, dominio, consulta, ctx):
            return {"dominio": dominio, "tenant": ctx.get("id_empresa"), "delegado": True}

    monkeypatch.setattr(agentes_mod, "manager", lambda: _FakeMgr())
    from src.services import agents_platform as ap
    r = ap.agente("compras").consultar("¿stock?", id_empresa="EMP-A")
    assert r["delegado"] and r["dominio"] == "compras" and r["tenant"] == "EMP-A"


# ── Data Lake + BI ──────────────────────────────────────────────────────────────
def test_datalake_reusa_dw():
    from src.services import datalake as dl
    assert len(dl.DOMINIOS) >= 12
    d = dl.descriptor()
    assert "reutilizado" in d["almacen"]                 # reutiliza bi_corp.dw, no nuevo almacén
    assert set(dl.dashboards.listar()) >= {"ventas", "compras", "stock", "rrhh", "finanzas"}
    r = dl.dashboards.dashboard("ventas", id_empresa="EMP-A")
    assert r["ok"] and r["dominio"] == "ventas" and isinstance(r["kpis"], list)


def test_datalake_etl_delega(monkeypatch):
    import src.services.bi_corp.dw as dw

    def _fake_etl(**kw):
        return {"ok": True, "delegado": True, "dominios": kw.get("dominios")}

    monkeypatch.setattr(dw, "ejecutar_etl", _fake_etl)
    from src.services import datalake as dl
    r = dl.ejecutar_etl(dominios=["ventas"], id_empresa="EMP-A")
    assert r.get("delegado") is True         # el lago delega en el DW corporativo


# ── Multi-Tenant Cloud Manager ─────────────────────────────────────────────────
def test_cloud_manager_reusa_saas():
    from src.services import cloud_manager as cm
    assert set(cm.licencias_cloud.PLANES) == {"enterprise", "professional", "basic", "trial", "custom"}
    g = cm.monitorizacion.global_()
    assert "saas" in g and "sistema" in g and "salud" in g       # agrega servicios existentes
    vista = cm.vista_global()
    assert "empresas" in vista and "monitorizacion" in vista and "plataforma" in vista


# ── Integración en la plataforma (preparación microservicios) ───────────────────
def test_fase5_registrada_en_plataforma():
    plat.bootstrap()
    nombres = plat.registry.nombres()
    for esperado in ("mobile", "portal", "api_publica", "bpd", "agents_platform",
                     "datalake", "cloud_manager"):
        assert esperado in nombres
    # Descubribles por capacidad y con dependencias resueltas hacia la infra existente.
    assert "bpd" in [c.nombre for c in plat.discovery.por_capacidad("procesos")]
    assert plat.discovery.resolver_dependencias("bpd").get("workflow") is True
    assert plat.discovery.resolver_dependencias("agents_platform").get("ccp") is True
