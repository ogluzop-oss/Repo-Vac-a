"""B7 — Chaos testing: simulacion de caidas + recuperacion offline de tienda."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_simular_caidas(db):
    from src.services.resiliencia import chaos_testing as ct
    for esc in ("aeat", "verifactu", "email", "db"):
        r = ct.simular(esc, id_empresa=E)
        assert r["ok"] is True and r["tiempo_recuperacion_seg"] >= 0
    with pytest.raises(ValueError):
        ct.simular("inexistente", id_empresa=E)
    assert len(ct.historial(limite=10)) >= 1


def test_simular_offline_tienda(db):
    from src.services.resiliencia import chaos_testing as ct
    r = ct.simular_offline_tienda(8, id_empresa=E)
    assert r["ok"] is True
    assert sum(r["pendientes_despues"].values()) == 0   # sincronizado tras reconectar
