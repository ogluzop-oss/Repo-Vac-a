"""B7 — Edge node: modos online/offline/recuperacion + operacion aislada + reconexion."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_registro_y_modos(db):
    from src.services.resiliencia import edge_node
    assert edge_node.registrar(E, 5, nombre="Tienda 5")["ok"]
    assert edge_node.set_modo(E, 5, "offline")
    with pytest.raises(ValueError):
        edge_node.set_modo(E, 5, "zzz")
    est = edge_node.estado(E, 5)
    assert est["modo"] == "offline" and "offline" in est


def test_reconexion_sincroniza(db):
    from src.services.resiliencia import edge_node, offline_store
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT IGNORE INTO articulos (codigo,nombre,id_empresa) VALUES ('EDGE1','E',%s)", (E,))
        conn.commit()
    edge_node.registrar(E, 6)
    edge_node.entrar_offline(E, 6)
    offline_store.set_stock(E, "EDGE1", 10, id_tienda=6)
    import uuid
    offline_store.registrar_venta(E, f"v-{uuid.uuid4().hex[:8]}", {"lineas": [{"codigo": "EDGE1", "cantidad": 1}]},
                                  10, id_tienda=6)
    r = edge_node.reconectar(E, 6)
    assert r["ok"] and r["modo"] == "online"
    assert offline_store.pendientes_sync(E, id_tienda=6)["ventas"] == 0
