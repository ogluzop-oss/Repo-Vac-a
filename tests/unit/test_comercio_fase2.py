"""
Tests PCD · Fase 2 (RFC-CD-002/006): Transacción Comercial.

Verifica: entidad unificada (crear/obtener/listar), máquina de estados (transiciones válidas/
inválidas), eventos al timeline + Event Bus, historial de decisiones (N9), reconstrucción (Audit
Replay), WRITE-THROUGH desde pedidos_online (Strangler, sin duplicar efectos) y aislamiento
multiempresa (0 cruces).
"""

import pytest

EMP = "T-TX-A"
EMP_B = "T-TX-B"


@pytest.fixture
def limpio(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                      "transaccion_comercial"):
                cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            cur.execute("DELETE FROM pedidos_online WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            cur.execute("DELETE FROM pedidos_online_items WHERE id_pedido LIKE 't_tx_%'")
            conn.commit()
    _b(); yield; _b()


def test_crear_y_obtener(limpio):
    from src.services.comercio_digital import transacciones as tx
    tid = tx.crear(tipo="pedido", origen="web", id_empresa=EMP,
                   cliente={"nombre": "Ana", "email": "a@x.com"},
                   lineas=[{"codigo": "ART001", "nombre": "Leche", "cantidad": 2,
                            "precio_unitario": 1.5}])
    assert tid
    t = tx.obtener(tid, EMP)
    assert t["estado"] == "BORRADOR" and t["origen"] == "web"
    assert len(t["lineas"]) == 1 and float(t["total"]) == 3.0
    # TxCreated en el timeline.
    evs = tx.eventos(tid, EMP)
    assert any(e["tipo_evento"] == "TxCreated" for e in evs)


def test_maquina_de_estados(limpio):
    from src.services.comercio_digital import transacciones as tx
    tid = tx.crear(id_empresa=EMP, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 10}])
    # Transición inválida (BORRADOR → ENVIADA).
    assert tx.transicionar(tid, "ENVIADA", id_empresa=EMP)["ok"] is False
    # Camino válido.
    assert tx.transicionar(tid, "CONFIRMADA", id_empresa=EMP, actor="op")["ok"]
    assert tx.transicionar(tid, "PAGADA", id_empresa=EMP)["ok"]
    assert tx.obtener(tid, EMP)["estado"] == "PAGADA"
    # Estado inexistente.
    assert tx.transicionar(tid, "XXX", id_empresa=EMP)["ok"] is False
    # Eventos TxConfirmed/TxPaid registrados.
    tipos = {e["tipo_evento"] for e in tx.eventos(tid, EMP)}
    assert {"TxCreated", "TxConfirmed", "TxPaid"} <= tipos


def test_decisiones_y_reconstruccion(limpio):
    from src.services.comercio_digital import transacciones as tx
    tid = tx.crear(id_empresa=EMP, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 5}])
    assert tx.registrar_decision(tid, motor="fulfillment", decision="origen=central",
                                 motivo="equilibrado", entradas={"buckets": 2},
                                 resultado={"origen": "central"}, actor="motor", id_empresa=EMP)
    r = tx.reconstruir(tid, EMP)
    assert r["transaccion"]["id_tx"] == tid
    assert r["decisiones"] and r["decisiones"][0]["motor"] == "fulfillment"
    assert any(e["tipo_evento"] == "TxCreated" for e in r["eventos"])


def test_write_through_desde_pedido(limpio):
    from src.services.comercio_digital import transacciones as tx
    from src.db import conexion as CX
    # Inserta un pedido_online directamente (simula el canal) y espeja.
    pid = "t_tx_ped1"
    with CX.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO pedidos_online (id_pedido, id_empresa, estado, plataforma, total, "
                    "cliente_nombre) VALUES (%s,%s,'PAGADO','woocommerce',20,'Bob')", (pid, EMP))
        cur.execute("INSERT INTO pedidos_online_items (id_pedido, codigo_articulo, nombre, cantidad,"
                    " precio_unitario, subtotal) VALUES (%s,'A','Art',2,10,20)", (pid,))
        conn.commit()
    tid = tx.desde_pedido_online(pid)
    assert tid
    t = tx.obtener(tid, EMP)
    assert t["id_pedido_origen"] == pid and t["estado"] == "PAGADA" and t["origen"] == "woocommerce"
    # Idempotente: no crea un segundo espejo.
    assert tx.desde_pedido_online(pid) == tid


def test_aislamiento_multiempresa(limpio):
    from src.services.comercio_digital import transacciones as tx
    a = tx.crear(id_empresa=EMP, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 1}])
    tx.crear(id_empresa=EMP_B, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 1}])
    # EMP_B no ve la transacción de EMP.
    assert tx.obtener(a, EMP_B) is None
    ids_a = {t["id_tx"] for t in tx.listar(id_empresa=EMP, id_tienda=None)}
    ids_b = {t["id_tx"] for t in tx.listar(id_empresa=EMP_B, id_tienda=None)}
    assert a in ids_a and a not in ids_b


def test_pedidos_online_intacto(limpio, monkeypatch):
    """El write-through NO rompe crear_pedido_online (Strangler): el pedido se crea igual y, además,
    se espeja en la Transacción."""
    from src.db.empresa import set_empresa_actual
    set_empresa_actual(EMP)
    from src.services.tpv import online_orders_service as OS
    pid = OS.crear_pedido_online({"nombre": "Cli"}, [{"codigo": "A", "nombre": "Art",
                                 "cantidad": 1, "precio": 5}], plataforma="interno")
    assert pid and OS.obtener_pedido(pid) is not None      # pedido_online sigue funcionando
    from src.services.comercio_digital import transacciones as tx
    # y quedó espejado como Transacción Comercial.
    with __import__("src.db.conexion", fromlist=["x"]).obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_tx FROM transaccion_comercial WHERE id_pedido_origen=%s", (pid,))
        assert cur.fetchone() is not None
