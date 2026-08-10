"""
Tests Fase III — infraestructura Enterprise (B1…B8). Un fichero, funciones por bloque.

Cada bloque valida su servicio (API-First, sin PyQt) y el aislamiento multiempresa donde aplique.
"""

import pytest

EMP = "T-F3-A"
EMP_B = "T-F3-B"


# ── B1 · Corporate Event Bus ──────────────────────────────────────────────────
def test_b1_eventbus(db):
    from src.services import eventbus
    # Catálogo estándar.
    cat = eventbus.catalogo()
    assert "CommunicationSent" in cat and "InvoicePaid" in cat and "PluginInstalled" in cat
    eventbus.registrar_evento("TestEvent", categoria="test", descripcion="prueba")
    assert "TestEvent" in eventbus.catalogo()
    # Suscripción + publicación (handler en proceso).
    recibidos = []
    eventbus.subscribe("TestEvent", lambda ev: recibidos.append(ev))
    ev = eventbus.publish("TestEvent", id_empresa=EMP, ref_entidad="x", ref_id="1",
                          payload={"a": 1})
    assert ev and ev.get("id")
    assert recibidos and recibidos[0].get("tipo") == "TestEvent"
    eventbus.unsubscribe("TestEvent", recibidos.append)
    # Replay (histórico por tipo/empresa).
    ev2 = eventbus.publish("TestEvent", id_empresa=EMP, ref_entidad="x", ref_id="2")
    rep = eventbus.replay(tipo="TestEvent", id_empresa=EMP)
    ids = {str(e.get("id")) for e in rep}
    assert str(ev["id"]) in ids and str(ev2["id"]) in ids
    # Multiempresa: EMP_B no ve los eventos de EMP.
    rep_b = eventbus.replay(tipo="TestEvent", id_empresa=EMP_B)
    assert str(ev["id"]) not in {str(e.get("id")) for e in rep_b}


# ── B2 · Enterprise REST API ──────────────────────────────────────────────────
def test_b2_rest_api(db):
    pytest.importorskip("flask")
    from src.api import crear_app
    from src.seguridad import tokens
    from src.db import correo as correo_db
    bid = correo_db.crear_correo("plataforma@f3api.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    app = crear_app(); cli = app.test_client()
    # Público: health + OpenAPI.
    assert cli.get("/api/v1/system/health").status_code == 200
    spec = cli.get("/api/v1/openapi.json").get_json()
    assert spec["openapi"].startswith("3.") and "/communications" in spec["paths"]
    assert "bearerAuth" in spec["components"]["securitySchemes"]
    # Sin auth → 401.
    assert cli.post("/api/v1/communications", json={"destinatario": "x@y.com"}).status_code == 401
    # Con JWT (tenant EMP) → envía por la CCP.
    tok = tokens.emitir_access({"id": "u1", "id_empresa": EMP, "perfil": "ADMINISTRADOR",
                                "nombre": "tester"})
    h = {"Authorization": f"Bearer {tok}"}
    r = cli.post("/api/v1/communications", json={"destinatario": "api@dest.com", "asunto": "Hola",
                                                 "cuerpo": "b"}, headers=h)
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["com_id"]
    # Historial del tenant EMP (aislado).
    hist = cli.get("/api/v1/communications", headers=h).get_json()
    assert all(x.get("id_empresa") == EMP for x in hist)
    # Token de EMP_B no ve las comunicaciones de EMP.
    tok_b = tokens.emitir_access({"id": "u2", "id_empresa": EMP_B, "perfil": "ADMINISTRADOR"})
    hist_b = cli.get("/api/v1/communications", headers={"Authorization": f"Bearer {tok_b}"}).get_json()
    assert all(x.get("id_empresa") == EMP_B for x in hist_b)
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_comunicaciones", "ccp_conversaciones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()


# ── B3 · Enterprise Scheduler ─────────────────────────────────────────────────
def test_b3_scheduler(db):
    from src.services import scheduler_enterprise as sched
    ejec = []
    sched.registrar_job("test_ok", lambda p: ejec.append(p))
    sid = sched.crear_schedule("Job OK", "test_ok", tipo="inmediata", params={"x": 1}, id_empresa=EMP)
    r = sched.ejecutar_schedule(sid)
    assert r["ok"] and ejec and ejec[0]["x"] == 1
    # Reintentos ante fallo.
    def _falla(p):
        raise RuntimeError("boom")
    sched.registrar_job("test_falla", _falla)
    sid2 = sched.crear_schedule("Job KO", "test_falla", tipo="inmediata", max_reintentos=1,
                                id_empresa=EMP)
    r2 = sched.ejecutar_schedule(sid2)
    assert not r2["ok"] and r2["intentos"] == 2
    # Multiempresa.
    assert all(s["id_empresa"] == EMP for s in sched.listar_schedules(EMP))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM scheduler_ejecuciones WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM scheduler_schedules WHERE id_empresa=%s", (EMP,))
        conn.commit()


# ── B4 · Plugin SDK ───────────────────────────────────────────────────────────
def test_b4_plugin_sdk(db):
    from src import sdk
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM plugins_instalados WHERE clave='ejemplo'")
        conn.commit()
    res = sdk.cargar_plugin("plugins/ejemplo")
    assert res["ok"] and res["clave"] == "ejemplo"
    menus = [e["valor"]["clave"] for e in sdk.extensiones("menus")]
    assert "ejemplo" in menus
    assert "ejemplo:iniciado" in sdk.ejecutar_hook("al_iniciar")
    assert any(p["clave"] == "ejemplo" for p in sdk.listar_instalados())
    assert sdk.desinstalar("ejemplo")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM plugins_instalados WHERE clave='ejemplo'")
        conn.commit()


# ── B5 · Corporate Rules Engine ───────────────────────────────────────────────
def test_b5_rules(db):
    from src.services import rules
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rules WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()
    rules.crear_regla("Factura grande", evento="InvoiceGenerated",
                      condiciones=[{"campo": "importe", "op": ">", "valor": 5000}],
                      acciones=[{"tipo": "lanzar_evento", "evento": "BigInvoice"}], id_empresa=EMP)
    disp = rules.evaluar_evento("InvoiceGenerated", {"importe": 6000}, id_empresa=EMP)
    assert disp["disparadas"] and disp["disparadas"][0]["acciones"][0]["ok"]
    # No se cumple → no dispara.
    disp2 = rules.evaluar_evento("InvoiceGenerated", {"importe": 1000}, id_empresa=EMP)
    assert disp2["disparadas"] == []
    # Multiempresa: EMP_B no tiene reglas.
    assert rules.evaluar_evento("InvoiceGenerated", {"importe": 9000}, id_empresa=EMP_B)["disparadas"] == []
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rules WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()


# ── B6 · Audit Replay ─────────────────────────────────────────────────────────
def test_b6_audit_replay(db):
    from src.db import correo as correo_db
    from src.services import ccp, audit_replay, eventbus
    bid = correo_db.crear_correo("plataforma@f3rep.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_comunicaciones WHERE id_empresa=%s", (EMP,))
        conn.commit()
    r = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="rep@x.com", asunto="Doc", cuerpo="b")
    eventbus.publish("CommunicationSent", id_empresa=EMP, ref_entidad="comunicacion", ref_id=r.com_id)
    rec = audit_replay.reconstruir(id_empresa=EMP, com_id=r.com_id)
    assert rec["resumen"]["total"] >= 1
    assert any(it["fuente"] == "comunicacion" for it in rec["cronologia"])
    assert "Reconstrucción" in audit_replay.a_texto(rec)
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_comunicaciones", "ccp_conversaciones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()


# ── B7 · Enterprise Observability / B8 · GraphQL-prep ─────────────────────────
def test_b7_b8(db):
    from src.services.observabilidad import dashboards
    d = dashboards.dashboard("scheduler", EMP)
    assert "activos" in d
    assert isinstance(dashboards.alertas(EMP), list)
    glob = dashboards.resumen_global(EMP)
    assert set(dashboards.DOMINIOS) <= set(glob)
    from src.api import graphql
    esq = graphql.esquema_previsto()
    assert "Communication" in esq["tipos"] and esq["consultas"]


# ── API-First: la infraestructura Fase III no importa PyQt ────────────────────
def test_apifirst_infra_sin_pyqt():
    import importlib
    import pkgutil
    ofensores = []
    for paquete in ("src.services.eventbus", "src.api", "src.services.rules",
                    "src.services.audit_replay", "src.services.scheduler_enterprise", "src.sdk"):
        pkg = importlib.import_module(paquete)
        for mod in pkgutil.walk_packages(pkg.__path__, prefix=paquete + "."):
            try:
                m = importlib.import_module(mod.name)
            except Exception:
                continue
            f = getattr(m, "__file__", None)
            if f and ("PyQt6" in open(f, encoding="utf-8").read()):
                ofensores.append(mod.name)
    assert ofensores == [], f"infra Fase III con PyQt (rompe API-First): {ofensores}"
