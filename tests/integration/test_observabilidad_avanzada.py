"""
Observabilidad avanzada (Bloque OBS) — correlation-id, health/ready/live, métricas Prometheus
degradable, alertas técnicas, incidentes, tracing degradable y endpoints HTTP de la API.
"""

import pytest

pytestmark = pytest.mark.db


def test_correlation():
    from src.services.observabilidad import correlation as C
    with C.contexto(prefijo="t") as cid:
        assert cid and C.get_id() == cid


def test_health(db):
    from src.services.observabilidad import health
    assert health.live()["status"] == "ok"
    assert health.ready()["status"] == "ok"
    h = health.health()
    assert "subsistemas" in h and h["subsistemas"]["db"] is True


def test_metricas():
    from src.services.observabilidad import metricas as M
    M.inc("sm_test_total", 2); M.set_gauge("sm_test_gauge", 7); M.observe("sm_test_lat", 0.1)
    assert "sm_test" in M.render()


def test_alertas_e_incidentes(db):
    from src.services.observabilidad import alertas_tecnicas as A
    from src.services.seguridad import incidentes as I
    r = A.emitir("salud", "BD lenta", severidad="alta", crear_incidente=True)
    iid = r["incidente"]; assert iid
    try:
        assert I.cambiar_estado(iid, "investigando")
        assert I.cambiar_estado(iid, "cerrado")
        with pytest.raises(ValueError):
            I.cambiar_estado(iid, "inventado")
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM eventos_incidentes WHERE id_incidente=%s", (iid,))
            cur.execute("DELETE FROM incidentes_seguridad WHERE id=%s", (iid,))
            conn.commit()


def test_tracing_degradable():
    from src.services.observabilidad import tracing
    with tracing.span("op_test") as sp:
        if sp:
            sp.set_attribute("k", "v")
    assert tracing.disponible() in (True, False)


def test_endpoints_http(db):
    try:
        from src.backend.app import crear_app
    except Exception:
        pytest.skip("Flask no disponible")
    app = crear_app()
    c = app.test_client()
    assert c.get("/api/v1/live").status_code == 200
    assert c.get("/api/v1/ready").status_code in (200, 503)
    assert c.get("/api/v1/metrics").status_code == 200
    r = c.get("/api/v1/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Correlation-ID")
