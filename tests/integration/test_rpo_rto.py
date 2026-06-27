"""B7 — RPO/RTO operativo por empresa y tienda (amplia DR)."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_rpo_rto_empresa(db):
    from src.services.resiliencia import rpo_rto
    r = rpo_rto.rpo_rto_empresa(id_empresa=E)
    assert "eventos_pendientes" in r and "perdida_potencial_eventos" in r


def test_rpo_rto_tienda(db):
    from src.services.resiliencia import offline_store, rpo_rto
    offline_store.inicializar(E, 3)
    r = rpo_rto.rpo_rto_tienda(3, id_empresa=E)
    assert r["id_tienda"] == 3 and "rto_estimado_seg" in r


def test_resumen(db):
    from src.services.resiliencia import rpo_rto
    r = rpo_rto.resumen(id_empresa=E)
    assert "empresa" in r and "tiendas" in r


def test_rbac_resiliencia(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN ('resiliencia.ver','resiliencia.sync','resiliencia.chaos')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"resiliencia.ver", "resiliencia.sync", "resiliencia.chaos"} <= enc
