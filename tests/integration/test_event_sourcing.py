"""B7 — Event sourcing operativo: eventos encadenados, replay, snapshot, integridad."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_replay_reconstruye_estado(db):
    from src.services.resiliencia import event_sourcing as es
    ag = f"ES{uuid.uuid4().hex[:6]}"
    es.registrar_evento("ENTRADA", "articulo", ag, {"cantidad": 100}, id_empresa=E)
    es.registrar_evento("SALIDA", "articulo", ag, {"cantidad": 40}, id_empresa=E)
    es.registrar_evento("ENTRADA", "articulo", ag, {"cantidad": 10}, id_empresa=E)
    r = es.replay("articulo", ag, id_empresa=E)
    assert r["estado"]["cantidad"] == 70.0 and r["eventos_aplicados"] == 3


def test_snapshot_acelera_replay(db):
    from src.services.resiliencia import event_sourcing as es
    ag = f"ES{uuid.uuid4().hex[:6]}"
    es.registrar_evento("ENTRADA", "articulo", ag, {"cantidad": 50}, id_empresa=E)
    snap = es.crear_snapshot("articulo", ag, id_empresa=E)
    assert snap["ok"] and snap["estado"]["cantidad"] == 50.0
    es.registrar_evento("SALIDA", "articulo", ag, {"cantidad": 20}, id_empresa=E)
    r = es.replay("articulo", ag, id_empresa=E)
    assert r["estado"]["cantidad"] == 30.0 and r["desde_snapshot"] >= 1   # parte del snapshot


def test_idempotencia_y_cadena(db):
    from src.services.resiliencia import event_sourcing as es
    ag = f"ES{uuid.uuid4().hex[:6]}"
    idem = f"ev-{uuid.uuid4().hex[:8]}"
    es.registrar_evento("ENTRADA", "articulo", ag, {"cantidad": 5}, idempotency_key=idem, id_empresa=E)
    r = es.registrar_evento("ENTRADA", "articulo", ag, {"cantidad": 5}, idempotency_key=idem, id_empresa=E)
    assert r["duplicado"] is True
    assert es.verificar_cadena(id_empresa=E)["ok"] is True
