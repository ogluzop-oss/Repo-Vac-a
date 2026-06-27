"""B7 — Circuit breakers: closed/open/half_open, fail-fast, fallback, recuperacion."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_apertura_y_failfast(db):
    from src.services.resiliencia import circuit_breaker as cb
    svc = f"svc{uuid.uuid4().hex[:6]}"
    assert cb.permitido(svc, id_empresa=E) is True
    for _ in range(6):
        cb.registrar_fallo(svc, id_empresa=E)
    assert cb.permitido(svc, id_empresa=E) is False   # abierto -> fail fast
    assert any(b["servicio"] == svc for b in cb.abiertos(id_empresa=E))


def test_exito_cierra(db):
    from src.services.resiliencia import circuit_breaker as cb
    svc = f"svc{uuid.uuid4().hex[:6]}"
    for _ in range(6):
        cb.registrar_fallo(svc, id_empresa=E)
    cb.registrar_exito(svc, id_empresa=E)
    assert cb.permitido(svc, id_empresa=E) is True


def test_llamar_con_fallback(db):
    from src.services.resiliencia import circuit_breaker as cb
    svc = f"svc{uuid.uuid4().hex[:6]}"
    # funcion que falla -> usa fallback y registra fallo
    r = cb.llamar(svc, lambda: (_ for _ in ()).throw(RuntimeError("boom")), id_empresa=E, fallback="degradado")
    assert r == "degradado"
    # funcion ok -> ejecuta
    assert cb.llamar(svc, lambda: "ok", id_empresa=E) == "ok"
