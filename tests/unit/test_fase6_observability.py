"""
Tests Fase VI · Bloque 12: Cloud Observability.

Verifica: tracing distribuido (Trace/Span/Correlation/Communication/Workflow ID + propagación),
métricas cloud (nodos/regiones/clústeres), logging centralizado (preparado ELK/OpenSearch/Loki),
alertas cloud y el Cloud Dashboard — todo reutilizando la Observabilidad Enterprise.
"""

import pytest

from src.platform import cloud
from src.services.observabilidad import cloud as obs


@pytest.fixture(autouse=True)
def _limpio():
    cloud.nodes.limpiar(); obs.log_collector.limpiar()
    yield
    cloud.nodes.limpiar(); obs.log_collector.limpiar()


def test_tracing_distribuido():
    t = obs.tracing.nuevo_trace(communication_id="COM-9", workflow_id="WF-3")
    hijo = t.hijo()
    # Misma traza, span hijo enlazado al padre; IDs corporativos propagados.
    assert hijo.trace_id == t.trace_id
    assert hijo.parent_span == t.span_id
    assert hijo.communication_id == "COM-9" and hijo.workflow_id == "WF-3"
    h = t.headers()
    assert h["X-Trace-Id"] == t.trace_id and h["X-Communication-Id"] == "COM-9"
    # Reconstrucción desde cabeceras (otro nodo).
    rec = obs.tracing.desde_headers(h)
    assert rec.trace_id == t.trace_id and rec.parent_span == t.span_id


def test_metricas_cloud():
    cloud.nodes.registrar("n1", region="eu", latencia_ms=10, carga=0.2)
    cloud.nodes.registrar("n2", region="am", latencia_ms=20, carga=0.4)
    m = obs.metricas_cloud.metricas_nodos()
    assert m["total"] == 2 and m["disponibles"] == 2
    regs = obs.metricas_cloud.metricas_regiones()
    assert set(regs.keys()) == {"eu", "am"}
    assert set(obs.metricas_cloud.dashboards()) >= {"nodos", "regiones", "eventbus", "workflow", "ccp"}


def test_logging_centralizado():
    assert set(obs.log_collector.BACKENDS) == {"local", "elk", "opensearch", "loki"}
    obs.log_collector.configurar("local")
    obs.log_collector.recolectar("error", "fallo", servicio="api", nodo="n1", region="eu")
    obs.log_collector.recolectar("info", "ok", servicio="ccp")
    assert obs.log_collector.descriptor()["eventos_bufferizados"] == 2
    assert len(obs.log_collector.consultar(nivel="error")) == 1


def test_alertas_cloud():
    cloud.nodes.registrar("lento", region="eu", latencia_ms=900, carga=0.97)
    cloud.nodes.registrar("degradado", region="eu", estado=cloud.nodes.DEGRADED)
    tipos = {a["tipo"] for a in obs.alertas_cloud.evaluar()}
    assert "latencia_alta" in tipos and "nodo_lento" in tipos and "nodo_degradado" in tipos


def test_cloud_dashboard():
    cloud.nodes.registrar("n1", region="eu")
    panel = obs.dashboard_cloud.panel()
    for clave in ("nodos", "regiones", "clusteres", "alertas", "logs", "salud_plataforma"):
        assert clave in panel
