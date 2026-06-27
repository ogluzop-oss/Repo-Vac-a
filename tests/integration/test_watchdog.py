"""B7 — Watchdog/autoheal: diagnostico + acciones de recuperacion."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_diagnostico(db):
    from src.services.resiliencia import resilience_watchdog as wd
    d = wd.diagnosticar(id_empresa=E)
    assert {"subsistemas", "outbox_pendiente", "breakers_abiertos", "conflictos"} <= set(d.keys())


def test_reencola_agotados(db):
    from src.services.resiliencia import outbox, resilience_watchdog as wd
    # crea un outbox fallido con intentos agotados
    outbox.encolar("test", {"x": uuid.uuid4().hex}, id_empresa=E)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE sync_outbox SET estado='fallido', intentos=5 WHERE id_empresa=%s "
                    "AND entidad='test'", (E,))
        conn.commit()
    r = wd.ejecutar(id_empresa=E, aplicar=True)
    assert r["ok"]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM sync_outbox WHERE id_empresa=%s AND entidad='test' AND estado='pendiente'",
                    (E,))
        n = cur.fetchone()
        assert (n[0] if not isinstance(n, dict) else list(n.values())[0]) >= 1
        cur.execute("DELETE FROM sync_outbox WHERE id_empresa=%s AND entidad='test'", (E,))
        conn.commit()
