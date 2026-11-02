"""Fase C — Stock en Consignación.

Recepción B2B en consignación sin pasivo (PMP intacto, sin escrow), disparador de liquidación en
`lotes.consumir_fefo` (idempotente, FIFO entre depósitos), y devolución sin impacto financiero.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import compras as C, lotes as L, proveedores as PROV
from src.db.conexion import obtener_conexion
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.comercio_digital import transacciones as TX
from src.services.compras import b2b_pedidos as B2B

E = EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _art(fab, db):
    cod = fab.articulo()

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "lotes_movimientos", "movimientos_stock"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
            conn.commit()
    fab.al_limpiar(_lim)
    return cod


def _suministrador(fab, db):
    razon = "Prov Consig " + uuid.uuid4().hex[:8]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO suministradores (razon_social, cif, email_login) VALUES (%s,%s,%s)",
                    (razon, "X" + uuid.uuid4().hex[:8].upper(), f"{uuid.uuid4().hex[:8]}@test.local"))
        id_sum = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: fab._borrar("suministradores", "id", id_sum))
    id_prov = PROV.crear_proveedor(razon, id_empresa=E)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE proveedores SET id_suministrador=%s WHERE id_proveedor=%s",
                    (id_sum, id_prov))
        conn.commit()
    fab.al_limpiar(lambda: fab._borrar("proveedores", "id_proveedor", id_prov))
    return id_sum, id_prov


def _tx_consignacion(fab, db, id_sum, codigo, cantidad, precio):
    id_tx = TX.crear(tipo="pedido", origen="b2b", estado="BORRADOR", id_empresa=E,
                     lineas=[{"codigo": codigo, "nombre": "Art Consig", "cantidad": cantidad,
                             "precio_unitario": precio}])
    assert id_tx

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM b2b_consignacion_movimientos WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM b2b_consignacion_saldo WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_lineas WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
            conn.commit()
    fab.al_limpiar(_lim)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE transaccion_comercial SET id_suministrador=%s, es_consignacion=1 "
                    "WHERE id_tx=%s", (id_sum, id_tx))
        conn.commit()
    tr = TX.transicionar(id_tx, "CONFIRMADA", actor="test", id_empresa=E)
    assert tr["ok"] is True
    return id_tx


def _saldo(db, id_tx, codigo):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM b2b_consignacion_saldo WHERE id_tx=%s AND codigo_articulo=%s",
                   (id_tx, codigo))
        row = cur.fetchone()
        return _fila(cur, row) if row else None


# ── Recepción: sin PMP, sin escrow, lote marcado consignación ────────────────
def test_recepcion_consignacion_sin_pasivo(db, fab):
    cod = _art(fab, db)
    id_sum, id_prov = _suministrador(fab, db)
    id_tx = _tx_consignacion(fab, db, id_sum, cod, 10, 7.50)

    assert C.obtener_costes(cod).get("coste_medio", 0) in (0, 0.0, None)
    r = B2B.recibir_mercancia(id_tx, actor="test", id_empresa=E)
    assert r["ok"] is True

    # La recepción en consignación NUNCA toca el PMP (mercancía todavía no es propiedad de la empresa).
    assert C.obtener_costes(cod)["coste_medio"] == 0.0

    saldo = _saldo(db, id_tx, cod)
    assert saldo is not None
    assert int(saldo["cantidad_depositada"]) == 10
    assert float(saldo["precio_unitario"]) == 7.50

    lotes_ = L.stock_por_lote(cod, id_empresa=E)
    assert any(l["propiedad"] == "consignacion" and l["id_suministrador"] == id_sum for l in lotes_)

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                   "AND TABLE_NAME='b2b_escrow'")
        existe_escrow = list(_fila(cur, cur.fetchone()).values())[0]
        if existe_escrow:
            cur.execute("SELECT COUNT(*) FROM b2b_escrow WHERE id_tx=%s", (id_tx,))
            n = list(_fila(cur, cur.fetchone()).values())[0]
            assert int(n) == 0


# ── Consumo: liquidación idempotente + FIFO entre depósitos ─────────────────
def test_consumo_liquida_una_sola_vez_y_fifo_multi_deposito(db, fab):
    cod = _art(fab, db)
    id_sum, id_prov = _suministrador(fab, db)
    id_tx1 = _tx_consignacion(fab, db, id_sum, cod, 10, 7.50)
    assert B2B.recibir_mercancia(id_tx1, actor="test", id_empresa=E)["ok"] is True
    id_tx2 = _tx_consignacion(fab, db, id_sum, cod, 5, 8.00)
    assert B2B.recibir_mercancia(id_tx2, actor="test", id_empresa=E)["ok"] is True

    def _lim_facturas():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_factura FROM compras_facturas WHERE numero_factura LIKE %s",
                       (f"CONSIG-{id_sum}-%",))
            for row in cur.fetchall():
                fid = row[0] if not isinstance(row, dict) else row["id_factura"]
                cur.execute("DELETE FROM compras_facturas_lineas WHERE id_factura=%s", (fid,))
                cur.execute("DELETE FROM compras_facturas WHERE id_factura=%s", (fid,))
            conn.commit()
    fab.al_limpiar(_lim_facturas)

    id_doc = "TEST-VENTA-" + uuid.uuid4().hex[:8]
    rc = L.consumir_fefo(cod, 12, tipo="SALIDA_VENTA", id_empresa=E, id_documento=id_doc,
                         usuario="test")
    assert rc["consumido"] == 12

    s1 = _saldo(db, id_tx1, cod)
    s2 = _saldo(db, id_tx2, cod)
    # FIFO: el depósito más antiguo (tx1, 10 uds) se agota primero; el resto (2) sale de tx2.
    assert int(s1["cantidad_consumida"]) == 10
    assert int(s2["cantidad_consumida"]) == 2

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_factura, base FROM compras_facturas WHERE numero_factura LIKE %s",
                   (f"CONSIG-{id_sum}-%",))
        facturas = [_fila(cur, r) for r in cur.fetchall()]
    assert len(facturas) == 1
    assert abs(float(facturas[0]["base"]) - 91.0) < 0.01     # 10*7.50 + 2*8.00

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM b2b_consignacion_movimientos WHERE tipo='LIQUIDACION' "
                   "AND id_documento=%s", (id_doc,))
        n_liq = list(_fila(cur, cur.fetchone()).values())[0]
    assert int(n_liq) == 1

    # Idempotencia: reintentar el MISMO evento de consumo (misma id_documento) no debe facturar de nuevo.
    r_retry = B2B.registrar_consumo_consignacion(id_sum, cod, 12, id_doc, E, usuario="test")
    assert r_retry["ok"] is False and r_retry.get("motivo") == "ya_liquidado"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM compras_facturas WHERE numero_factura LIKE %s",
                   (f"CONSIG-{id_sum}-%",))
        n_fact = list(_fila(cur, cur.fetchone()).values())[0]
    assert int(n_fact) == 1


# ── Devolución: sin impacto financiero, valida disponible ────────────────────
def test_devolucion_sin_factura_y_valida_disponible(db, fab):
    cod = _art(fab, db)
    id_sum, id_prov = _suministrador(fab, db)
    id_tx = _tx_consignacion(fab, db, id_sum, cod, 6, 3.0)
    assert B2B.recibir_mercancia(id_tx, actor="test", id_empresa=E)["ok"] is True

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM compras_facturas")
        n_antes = list(_fila(cur, cur.fetchone()).values())[0]

    r = B2B.solicitar_devolucion_consignacion(id_tx, cod, 4, actor="test")
    assert r["ok"] is True and r["devuelto"] == 4

    saldo = _saldo(db, id_tx, cod)
    assert int(saldo["cantidad_devuelta"]) == 4

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM compras_facturas")
        n_despues = list(_fila(cur, cur.fetchone()).values())[0]
    assert n_antes == n_despues            # ninguna factura generada por la devolución

    r_excede = B2B.solicitar_devolucion_consignacion(id_tx, cod, 999, actor="test")
    assert r_excede["ok"] is False and r_excede["error"] == "cantidad_supera_disponible"
