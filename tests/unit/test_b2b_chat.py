"""Tests · Chat por pedido B2B (Smart Suppliers · Fase 3): mensajería, no-leídos y aislamiento."""
import uuid

import pytest

pytestmark = pytest.mark.db


def _crear_suministrador(db, nombre):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO suministradores (razon_social, cif, sector_id, email_login) "
                    "VALUES (%s,%s,%s,%s)",
                    (nombre, "R" + uuid.uuid4().hex[:8], 1, uuid.uuid4().hex[:8] + "@prov.test"))
        id_sum = cur.lastrowid
        conn.commit()
    return id_sum


def _crear_tx_b2b(db, id_empresa, id_suministrador):
    from src.services.comercio_digital import transacciones as TX
    id_tx = TX.crear(tipo="pedido", origen="b2b", estado="BORRADOR", id_empresa=id_empresa,
                     id_tienda=None,
                     lineas=[{"codigo": "X", "nombre": "X", "cantidad": 1, "precio_unitario": 1.0}])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE transaccion_comercial SET id_suministrador=%s WHERE id_tx=%s",
                    (id_suministrador, id_tx))
        conn.commit()
    return id_tx


def _limpiar(db, id_suministrador, *ids_tx):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for id_tx in ids_tx:
            cur.execute("DELETE FROM b2b_pedido_mensajes WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM b2b_pedido_lecturas WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_lineas WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
        cur.execute("DELETE FROM suministradores WHERE id=%s", (id_suministrador,))
        conn.commit()


def test_enviar_listar_marcar_leido(db, fab):
    from src.services.compras import b2b_chat as CHAT
    emp = fab.empresa("B2B3 CHAT")
    id_sum = _crear_suministrador(db, "Prov Chat")
    id_tx = _crear_tx_b2b(db, emp, id_sum)
    try:
        assert CHAT.no_leidos(id_tx, "empresa") == 0

        vacio = CHAT.enviar_mensaje(id_tx, "proveedor", "Juan", "  ")
        assert vacio["ok"] is False and vacio["error"] == "mensaje_vacio"

        r = CHAT.enviar_mensaje(id_tx, "proveedor", "Juan (proveedor)", "¿Confirmáis la entrega?")
        assert r["ok"]
        # La empresa aún no lo ha leído; el propio remitente no se cuenta a sí mismo como no-leído.
        assert CHAT.no_leidos(id_tx, "empresa") == 1
        assert CHAT.no_leidos(id_tx, "proveedor") == 0

        CHAT.marcar_leido(id_tx, "empresa")
        assert CHAT.no_leidos(id_tx, "empresa") == 0

        CHAT.enviar_mensaje(id_tx, "empresa", "Ana (empresa)", "Sí, mañana a las 10h.")
        msgs = CHAT.listar_mensajes(id_tx)
        assert len(msgs) == 2 and msgs[0]["autor_tipo"] == "proveedor" and msgs[1]["autor_tipo"] == "empresa"
        assert CHAT.no_leidos_totales_proveedor(id_sum) == 1
        assert CHAT.no_leidos_totales_empresa(emp) == 0   # la empresa acaba de enviar/leer
    finally:
        _limpiar(db, id_sum, id_tx)


def test_autorizacion_por_lado(db, fab):
    """Un proveedor no puede operar sobre un pedido que no es suyo (obtener_para_proveedor)."""
    from src.services.compras import b2b_pedidos as PED
    emp = fab.empresa("B2B3 CHAT AUTORIZ")
    id_sum_a = _crear_suministrador(db, "Prov Chat A")
    id_sum_b = _crear_suministrador(db, "Prov Chat B")
    id_tx = _crear_tx_b2b(db, emp, id_sum_a)
    try:
        assert PED.obtener_para_proveedor(id_tx, id_sum_a) is not None
        assert PED.obtener_para_proveedor(id_tx, id_sum_b) is None
        pedidos_a = PED.listar_para_suministrador(id_sum_a)
        pedidos_b = PED.listar_para_suministrador(id_sum_b)
        assert any(p["id_tx"] == id_tx for p in pedidos_a)
        assert not any(p["id_tx"] == id_tx for p in pedidos_b)
    finally:
        _limpiar(db, id_sum_a, id_tx)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM suministradores WHERE id=%s", (id_sum_b,))
            conn.commit()
