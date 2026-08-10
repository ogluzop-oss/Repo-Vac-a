"""
Tests Etapa F · Fase F1: observabilidad operacional.

Verifica que los gauges operacionales (Scheduler/Event Bus/Marketplace/SDK) se publican en el motor de
métricas ÚNICO (Prometheus) vía el recolector `operacional`, que quedan expuestos en `/api/v1/metrics`
junto a las métricas de API existentes, que los dashboards ganan los dominios eventbus/marketplace, y
que la correlación extremo a extremo (X-Correlation-ID) sigue funcionando. Sin duplicar observabilidad.
"""

import pytest

pytestmark = pytest.mark.db


def test_snapshot_estructura(db):
    from src.services.observabilidad import operacional
    snap = operacional.snapshot()
    assert set(snap) == {"scheduler", "eventbus", "marketplace", "sdk"}
    assert isinstance(snap["scheduler"], dict) and "ejecuciones_fallidas" in snap["scheduler"]
    assert "eventos_total" in snap["eventbus"]


def test_recolectar_publica_gauges_en_motor_unico(db):
    from src.services.observabilidad import metricas, operacional
    operacional.recolectar()
    render = metricas.render()
    for gauge in ("sm_scheduler_schedules_activos", "sm_eventbus_eventos_total",
                  "sm_marketplace_catalogo_total", "sm_sdk_plugins_instalados"):
        assert gauge in render, f"gauge ausente en Prometheus: {gauge}"


def test_metrics_endpoint_incluye_operacional_y_api(db):
    from src.backend.app import crear_app
    c = crear_app().test_client()
    # Una petición cualquiera incrementa el contador de API existente.
    c.get("/api/v1/live")
    r = c.get("/api/v1/metrics")
    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    assert "sm_api_requests_total" in cuerpo                 # métrica API existente (reutilizada)
    assert "sm_scheduler_schedules_activos" in cuerpo        # gauge operacional nuevo (F1)
    assert "sm_eventbus_eventos_total" in cuerpo


def test_dashboards_nuevos_dominios(db):
    from src.services.observabilidad import dashboards
    assert "eventbus" in dashboards.DOMINIOS and "marketplace" in dashboards.DOMINIOS
    eb = dashboards.dashboard("eventbus")
    mk = dashboards.dashboard("marketplace")
    assert isinstance(eb, dict) and "eventos_total" in eb
    assert isinstance(mk, dict)
    glob = dashboards.resumen_global()
    assert "eventbus" in glob and "marketplace" in glob     # resumen_global los incluye (aditivo)


def test_correlacion_extremo_a_extremo(db):
    from src.backend.app import crear_app
    c = crear_app().test_client()
    # Sin cabecera → el backend genera y devuelve un correlation-id.
    r1 = c.get("/api/v1/live")
    assert r1.headers.get("X-Correlation-ID") not in (None, "", "-")
    # Con cabecera → se propaga (mismo id en la respuesta).
    r2 = c.get("/api/v1/live", headers={"X-Correlation-ID": "corr-f1-test"})
    assert r2.headers.get("X-Correlation-ID") == "corr-f1-test"


def test_descriptor_no_motor_nuevo(db):
    from src.services.observabilidad import operacional
    d = operacional.descriptor()
    assert d["motor_nuevo"] is False and d["solo_lectura"] is True
    assert "observabilidad.metricas (Prometheus)" in d["reutiliza"]
    assert len(d["gauges"]) >= 9
