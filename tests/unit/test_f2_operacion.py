"""
Tests Etapa F · Fase F2: operación Enterprise (estado unificado).

Verifica la fachada `observabilidad.estado` (self-test, diagnóstico, estado global/por módulo/por
tenant) que COMPONE las piezas existentes (health/estado_sistema/operacional/watchdog), y su exposición
autenticada en `/api/v1/system/*` con aislamiento por tenant. Sin mecanismos nuevos, degradable.
"""

import pytest

pytestmark = pytest.mark.db


def test_global_incluye_live_ready_health(db):
    from src.services.observabilidad import estado
    g = estado.global_()
    assert "status" in g and "live" in g and "ready" in g and "subsistemas" in g
    assert g["live"].get("status") == "ok"                 # liveness reutiliza health.live


def test_por_modulo_combina_health_y_operacional(db):
    from src.services.observabilidad import estado
    m = estado.por_modulo()
    assert "db" in m                                       # subsistema de health
    # módulos operacionales (F1) con sus métricas
    for modulo in ("scheduler", "eventbus", "marketplace", "sdk"):
        assert modulo in m and "metricas" in m[modulo]


def test_por_tenant_aislado(db):
    from src.services.observabilidad import estado
    t = estado.por_tenant("T-F2-X")
    assert t["id_empresa"] == "T-F2-X"
    assert "operacional" in t and "ready" in t


def test_self_test_estructura_y_criticos(db):
    from src.services.observabilidad import estado
    r = estado.self_test()
    assert "ok" in r and isinstance(r["checks"], list) and r["total"] >= 4
    assert any(c["nombre"] == "db_accesible" and c["critico"] for c in r["checks"])
    # Con BD de test accesible, el check crítico de BD pasa.
    assert next(c for c in r["checks"] if c["nombre"] == "db_accesible")["ok"] is True


def test_diagnostico_reutiliza_watchdog(db):
    from src.services.observabilidad import estado
    d = estado.diagnostico()
    # Reutiliza el watchdog de resiliencia (subsistemas/colas/breakers) o degrada limpio.
    assert "id_empresa" in d
    assert "resiliencia" in d or "sistema" in d


def test_descriptor_no_motor_nuevo(db):
    from src.services.observabilidad import estado
    d = estado.descriptor()
    assert d["motor_nuevo"] is False and d["solo_lectura"] is True
    assert "observabilidad.health" in d["reutiliza"]
    assert set(d["operaciones"]) >= {"self_test", "diagnostico", "global_", "por_modulo", "por_tenant"}


# ── Exposición REST autenticada + aislamiento por tenant ──────────────────────
@pytest.fixture()
def cliente(db, monkeypatch):
    monkeypatch.setenv("API_MASTER_KEY", "clave_f2")
    from src.api import crear_app
    return crear_app().test_client()


def _h(emp="EMP-F2"):
    return {"X-API-Key": "clave_f2", "X-Empresa-Id": emp}


def test_status_requiere_auth(cliente):
    assert cliente.get("/api/v1/system/status").status_code == 401
    assert cliente.get("/api/v1/system/status", headers=_h()).status_code == 200


def test_status_modulos_y_tenant(cliente):
    r = cliente.get("/api/v1/system/status", headers=_h()).get_json()
    assert "global" in r and "modulos" in r and "scheduler" in r["modulos"]
    t = cliente.get("/api/v1/system/status/tenant", headers=_h("EMP-F2-A")).get_json()
    assert t["id_empresa"] == "EMP-F2-A"                   # tenant del token, no del cuerpo


def test_selftest_endpoint(cliente):
    r = cliente.get("/api/v1/system/selftest", headers=_h())
    assert r.status_code in (200, 503)
    j = r.get_json()
    assert "checks" in j and "ok" in j


def test_diagnostico_endpoint(cliente):
    r = cliente.get("/api/v1/system/diagnostico", headers=_h())
    assert r.status_code == 200 and "id_empresa" in r.get_json()
