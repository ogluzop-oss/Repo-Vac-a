"""B7 — Dashboard de resiliencia + cache manager + publicacion de metricas."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_panel(db):
    from src.services.resiliencia import resilience_dashboard as rd
    p = rd.panel(id_empresa=E)
    assert {"salud", "colas", "sync_pendientes", "circuit_breakers", "rpo_rto", "edge_nodes"} <= set(p.keys())


def test_publicar_metricas(db):
    from src.services.resiliencia import resilience_dashboard as rd
    from src.services.observabilidad import metricas
    rd.publicar_metricas(id_empresa=E)
    render = metricas.render()
    assert "sync_pending_total" in render or "circuit_breakers_open" in render


def test_cache_manager(db):
    from src.services.resiliencia import cache_manager as cm
    cm.set("k1", {"v": 1}, ttl=60)
    assert cm.get("k1") == {"v": 1}
    cm.invalidar("k1")
    assert cm.get("k1") is None
    assert cm.get_or_set("k2", lambda: 42, ttl=60) == 42
    assert cm.get("k2") == 42
    assert "entradas" in cm.estado()
