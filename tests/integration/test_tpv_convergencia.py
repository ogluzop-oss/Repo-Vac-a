"""
P0 · Convergencia del TPV/autocobro hacia la ruta canónica registrar_venta_con_items.

Valida que la ruta canónica ampliada persiste cliente/caja/granel/descuento y dispara
kárdex/FEFO/stock_almacen/contab, SIN doble decremento, y que TPV/autocobro ya NO usan
persistencia inline (delegan en la ruta canónica).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.conexion import registrar_venta_con_items
from src.db import kardex, lotes as L, stock_almacen as SA
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "movimientos_stock", "venta_items"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM ventas_errores WHERE codigo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    return cod


def _venta_row(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT total, numero_caja, cliente_id, cliente_nombre, cliente_nif, "
                    "id_empresa, id_tienda, id_almacen FROM ventas WHERE id=%s", (vid,))
        r = cur.fetchone()
        cols = ["total", "numero_caja", "cliente_id", "cliente_nombre", "cliente_nif",
                "id_empresa", "id_tienda", "id_almacen"]
        return dict(zip(cols, r)) if r and not isinstance(r, dict) else r


def _clean_venta(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
        cur.execute("DELETE FROM ventas WHERE id=%s", (vid,)); conn.commit()


# ── 1/2 venta simple y múltiple + ítems completos ────────────────────────────
def test_venta_simple_y_multiple(db, fab):
    c1 = _art(fab, db, stock_tienda=10); c2 = _art(fab, db, stock_tienda=10)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": c1, "nombre": "A", "seccion": "S", "cantidad": 2, "precio_unitario": 5,
              "subtotal": 10},
             {"codigo_articulo": c2, "cantidad": 1, "precio_unitario": 3, "subtotal": 3}],
            numero_caja=7)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo_articulo, nombre, seccion, subtotal FROM venta_items WHERE venta_id=%s", (vid,))
        items = cur.fetchall()
    assert len(items) == 2
    assert _venta_row(db, vid)["total"] == 13


# ── 3/4 con y sin cliente ────────────────────────────────────────────────────
def test_venta_con_cliente(db, fab):
    cod = _art(fab, db, stock_tienda=5)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 2,
                                          "subtotal": 2}],
                                        cliente={"id": 123, "nombre": "Ana", "nif": "12345678Z"})
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    r = _venta_row(db, vid)
    assert r["cliente_id"] == 123 and r["cliente_nombre"] == "Ana" and r["cliente_nif"] == "12345678Z"


def test_venta_sin_cliente(db, fab):
    cod = _art(fab, db, stock_tienda=5)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 2}])
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    assert _venta_row(db, vid)["cliente_id"] is None


# ── 5 descuento (subtotal real ≠ cantidad×precio) ────────────────────────────
def test_venta_con_descuento(db, fab):
    cod = _art(fab, db, stock_tienda=10)
    with contexto_tenant(E, None):
        # 2×10=20 pero subtotal real 15 (descuento) y total real 15
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 2, "precio_unitario": 10,
                                          "subtotal": 15}], total=15)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    assert _venta_row(db, vid)["total"] == 15


# ── 6 granel ──────────────────────────────────────────────────────────────────
def test_venta_granel(db, fab):
    cod = _art(fab, db, stock_tienda=100)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 0,
                                          "subtotal": 3.45, "peso_vendido": 1.5, "precio_kg": 2.30,
                                          "modo_venta": "GRANEL"}], total=3.45)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT peso_vendido, precio_kg, modo_venta FROM venta_items WHERE venta_id=%s", (vid,))
        r = cur.fetchone()
    assert float(r[0]) == 1.5 and r[2] == "GRANEL"


# ── 7 FEFO ───────────────────────────────────────────────────────────────────
def test_venta_consume_fefo(db, fab):
    cod = _art(fab, db, stock_tienda=20)
    tid = _min_tienda(db)
    with contexto_tenant(E, tid):
        L.registrar_entrada(cod, "LF", 20, id_empresa=E, id_tienda=tid,
                            id_almacen=SA.almacen_de_tienda(tid, E))
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 6, "precio_unitario": 1,
                                          "subtotal": 6}])
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    assert L.stock_total_en_lotes(cod, E, tid) == 14   # 20 - 6 (FEFO en la tienda activa)


def _min_tienda(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(id) FROM tiendas WHERE id_empresa=%s", (E,))
        r = cur.fetchone()
        return r[0] if not isinstance(r, dict) else list(r.values())[0]


# ── 8/11/12 gestionado: kárdex + stock_almacen + NO doble decremento ─────────
def test_kardex_stock_almacen_y_no_doble_decremento(db, fab):
    cod = _art(fab, db, stock_tienda=10)
    SA.reseed_articulo(cod, E)                       # gestionado
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 3, "precio_unitario": 1,
                                          "subtotal": 3}])
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s", (cod,))
        # decremento UNA sola vez: 10 - 3 = 7 (no 4)
        assert cur.fetchone()[0] == 7
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA")) == 1
    # stock_almacen sincronizado (sin divergencia)
    from src.db import reconciliacion as R
    assert all(d["codigo"] != cod for d in R.divergencias_stock(E))


# ── 10 evento contable ───────────────────────────────────────────────────────
def test_evento_contable(db, fab):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CONV")
    fab.al_limpiar(lambda: _borra_emp(db, emp))
    K.activar(emp, 2026)
    cod = _art(fab, db, stock_tienda=10)
    with contexto_tenant(emp, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 5,
                                          "subtotal": 5}], total=5, id_empresa=emp)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_cola WHERE id_empresa=%s AND evento='venta' "
                    "AND ref=%s", (emp, str(vid)))
        assert cur.fetchone()[0] == 1               # encolado para contabilizar


def _borra_emp(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,)); conn.commit()


# ── 14 caja + tenant ─────────────────────────────────────────────────────────
def test_caja_y_tenant(db, fab):
    cod = _art(fab, db, stock_tienda=5)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 1}],
                                        numero_caja=42, id_empresa=E)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    r = _venta_row(db, vid)
    assert r["numero_caja"] == 42 and r["id_empresa"] == E


# ── Compat hacia atrás (llamador antiguo de ventas_comercial) ────────────────
def test_compat_llamada_antigua(db, fab):
    cod = _art(fab, db, stock_tienda=10)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 2, "precio_unitario": 4}],
                                        empleado_id=None)   # firma mínima (como ventas_comercial)
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    assert vid and _venta_row(db, vid)["total"] == 8


# ── 15 estructura: TPV/autocobro ya no persisten inline ──────────────────────
def test_tpv_autocobro_sin_inline():
    import inspect
    from src.gui import tpv, autocobro
    fuente_tpv = inspect.getsource(tpv)
    fuente_ac = inspect.getsource(autocobro)
    # Ambos delegan en la ruta canónica…
    assert "registrar_venta_con_items" in fuente_tpv
    assert "registrar_venta_con_items" in fuente_ac
    # …y ya NO persisten la venta inline (sin INSERT INTO ventas ni UPDATE de stock de venta).
    assert "INSERT INTO ventas" not in fuente_tpv
    assert "INSERT INTO ventas" not in fuente_ac
    assert "UPDATE articulos SET Stock_tienda = GREATEST" not in fuente_ac
