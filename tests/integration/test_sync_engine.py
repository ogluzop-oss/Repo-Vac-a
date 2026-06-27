"""B7 — Motor de sincronizacion: drena offline->central, idempotente, reanudable."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def art(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT IGNORE INTO articulos (codigo,nombre,id_empresa) VALUES ('SYNC1','S',%s)", (E,))
        conn.commit()
    yield


def test_push_offline_a_central(db, art):
    from src.services.resiliencia import offline_store, sync_engine
    offline_store.inicializar(E, 7); offline_store.set_stock(E, "SYNC1", 10, id_tienda=7)
    offline_store.registrar_venta(E, f"v-{uuid.uuid4().hex[:8]}", {"lineas": [{"codigo": "SYNC1", "cantidad": 2}]},
                                  20, id_tienda=7)
    r = sync_engine.push_offline_a_central(id_empresa=E, id_tienda=7)
    assert r["ok"] and r["resumen"]["ventas"] >= 1
    assert offline_store.pendientes_sync(E, id_tienda=7)["ventas"] == 0
    # reanudable: segunda pasada no reprocesa
    r2 = sync_engine.push_offline_a_central(id_empresa=E, id_tienda=7)
    assert r2["resumen"]["ventas"] == 0


def test_pull_catalogo(db, art):
    from src.services.resiliencia import offline_store, sync_engine
    r = sync_engine.pull_central_a_offline(id_empresa=E, id_tienda=7)
    assert r["ok"] and r["sincronizado"]["articulos"] >= 1
    assert offline_store.articulo(E, "SYNC1", id_tienda=7) is not None
