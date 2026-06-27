"""
CRM comercial — leads, pipeline, oportunidades, actividades, automatizacion, CRM SaaS,
analitica, scoring IA, RBAC y auditoria.
"""

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


@pytest.fixture
def limpia_crm(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("crm_actividades", "crm_oportunidades", "crm_leads", "crm_saas_funnel"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s OR id_empresa IS NULL", (E,))
        conn.commit()


def test_leads_ciclo(db, limpia_crm):
    from src.services.crm import leads
    lid = leads.crear_lead("Lead Uno", empresa="Acme", email="a@b.com", valor_estimado=5000,
                           prioridad="alta", id_empresa=E)
    assert lid
    assert leads.actualizar_lead(lid, estado="calificado")
    with pytest.raises(ValueError):
        leads.actualizar_lead(lid, estado="zzz")
    assert any(l["id"] == lid for l in leads.listar_leads(id_empresa=E))
    conv = leads.convertir_a_cliente(lid, id_empresa=E)
    assert conv["ok"] and conv["id_cliente"]
    assert leads.obtener_lead(lid)["estado"] == "convertido"
    # idempotente
    assert leads.convertir_a_cliente(lid, id_empresa=E).get("ya_convertido")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (conv["id_cliente"],))
        conn.commit()


def test_pipeline_defecto(db):
    from src.services.crm import pipeline
    pid = pipeline.asegurar_pipeline_defecto(id_empresa=E)
    pid2 = pipeline.asegurar_pipeline_defecto(id_empresa=E)   # idempotente
    assert pid == pid2
    etapas = pipeline.listar_etapas(pid, id_empresa=E)
    assert len(etapas) == 7
    assert pipeline.etapa_por_codigo("ganado", id_empresa=E)["es_ganado"] == 1


def test_oportunidades_y_forecast(db, limpia_crm):
    from src.services.crm import oportunidades
    oid = oportunidades.crear_oportunidad("Op1", valor=10000, etapa_codigo="propuesta", id_empresa=E)
    assert oid
    vp = oportunidades.valor_pipeline(id_empresa=E)
    assert vp["valor_total"] >= 10000 and vp["valor_ponderado"] > 0
    r = oportunidades.mover_etapa(oid, "ganado", id_empresa=E)
    assert r["ok"] and r["estado"] == "ganada"
    # tras ganar, ya no cuenta como abierta
    assert oportunidades.valor_pipeline(id_empresa=E)["abiertas"] == 0


def test_actividades_reutiliza_infra(db, limpia_crm):
    from src.services.crm import actividades, leads
    lid = leads.crear_lead("Lead Act", id_empresa=E)
    aid = actividades.crear_actividad("llamada", "Primer contacto", id_lead=lid, id_empresa=E)
    assert aid
    with pytest.raises(ValueError):
        actividades.crear_actividad("xxx", "bad", id_empresa=E)
    assert any(a["id"] == aid for a in actividades.listar(id_lead=lid, id_empresa=E))
    assert actividades.completar(aid, id_empresa=E)


def test_scoring_y_priorizacion(db, limpia_crm):
    from src.services.crm import crm_scoring, leads
    alto = leads.crear_lead("Big", email="x@y.com", telefono="600", valor_estimado=50000,
                            prioridad="alta", id_empresa=E)
    bajo = leads.crear_lead("Small", valor_estimado=0, prioridad="baja", id_empresa=E)
    s_alto = crm_scoring.puntuar_lead(alto)["score"]
    s_bajo = crm_scoring.puntuar_lead(bajo)["score"]
    assert s_alto > s_bajo
    pr = crm_scoring.priorizar_leads(id_empresa=E)
    assert pr and pr[0]["id"] == alto
    fc = crm_scoring.forecast_comercial(id_empresa=E)
    assert "forecast_ponderado" in fc


def test_crm_saas_funnel(db, limpia_crm):
    from src.services.crm import crm_saas
    fid = crm_saas.crear_lead_saas("Prospect SaaS", plan_interes="PRO", valor_estimado=1200)
    assert fid
    assert crm_saas.avanzar_fase(fid, "demo")
    with pytest.raises(ValueError):
        crm_saas.avanzar_fase(fid, "zzz")
    r = crm_saas.convertir_a_cliente_saas(fid, "empresa-x")
    assert r["ok"]
    assert crm_saas.embudo().get("cliente", 0) >= 1


def test_analitica_kpis(db, limpia_crm):
    from src.services.crm import analitica, leads
    leads.crear_lead("L1", id_empresa=E)
    k = analitica.kpis(id_empresa=E)
    assert {"leads_nuevos", "conversion_pct", "tasa_cierre_pct", "valor_pipeline"} <= set(k.keys())


def test_automatizacion(db, limpia_crm):
    from src.services.crm import automatizacion, leads
    leads.crear_lead("Sin contacto", estado=None, id_empresa=E) if False else \
        leads.crear_lead("Sin contacto", id_empresa=E)
    r = automatizacion.ejecutar_reglas(id_empresa=E)
    assert "leads_sin_respuesta" in r and "oportunidades_estancadas" in r


def test_rbac_permisos_crm(db):
    """El catalogo incluye los permisos crm.* y dr.* tras sincronizar."""
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN ('crm.ver','crm.leads','crm.admin','dr.ver')")
        encontrados = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"crm.ver", "crm.leads", "crm.admin", "dr.ver"} <= encontrados
