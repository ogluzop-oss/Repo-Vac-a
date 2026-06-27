"""B7 — Offline Store SQLite: catalogo local, ventas/movimientos offline, idempotencia, integridad."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_inicializar_y_catalogo(db):
    from src.services.resiliencia import offline_store
    assert offline_store.inicializar(E, 9)["ok"]
    offline_store.upsert_articulo(E, "OFA1", "Art 1", {"codigo": "OFA1"}, id_tienda=9)
    offline_store.set_precio(E, "OFA1", 9.5, id_tienda=9)
    offline_store.set_stock(E, "OFA1", 100, id_tienda=9)
    assert offline_store.articulo(E, "OFA1", id_tienda=9)["nombre"] == "Art 1"
    assert offline_store.precio(E, "OFA1", id_tienda=9) == 9.5
    assert offline_store.consultar_stock(E, "OFA1", id_tienda=9) == 100.0


def test_venta_offline_idempotente_y_stock(db):
    from src.services.resiliencia import offline_store
    offline_store.inicializar(E, 9); offline_store.set_stock(E, "OFA2", 20, id_tienda=9)
    idem = f"v-{uuid.uuid4().hex[:8]}"
    r1 = offline_store.registrar_venta(E, idem, {"lineas": [{"codigo": "OFA2", "cantidad": 5}]}, 50, id_tienda=9)
    assert r1["ok"] and not r1.get("duplicado")
    assert offline_store.consultar_stock(E, "OFA2", id_tienda=9) == 15.0
    r2 = offline_store.registrar_venta(E, idem, {"lineas": []}, 50, id_tienda=9)
    assert r2["duplicado"] is True
    assert offline_store.consultar_stock(E, "OFA2", id_tienda=9) == 15.0   # no re-descuenta


def test_movimiento_y_pendientes(db):
    from src.services.resiliencia import offline_store
    tienda = 9000 + (uuid.uuid4().int % 900)   # tienda aislada (sin estado compartido entre runs)
    offline_store.inicializar(E, tienda)
    antes = offline_store.pendientes_sync(E, id_tienda=tienda)["movimientos"]
    offline_store.registrar_movimiento(E, f"m-{uuid.uuid4().hex[:8]}", "OFA3", "ENTRADA", 30, id_tienda=tienda)
    assert offline_store.consultar_stock(E, "OFA3", id_tienda=tienda) == 30.0
    pend = offline_store.pendientes_sync(E, id_tienda=tienda)
    assert pend["movimientos"] == antes + 1


def test_integridad_hash_chain(db):
    from src.services.resiliencia import offline_store
    offline_store.inicializar(E, 9)
    offline_store.registrar_venta(E, f"v-{uuid.uuid4().hex[:8]}", {"lineas": []}, 10, id_tienda=9)
    assert offline_store.verificar_integridad(E, id_tienda=9)["ok"] is True
