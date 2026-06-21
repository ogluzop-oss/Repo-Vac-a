"""
INV.4 · Multialmacén real (stock_almacen como fuente de verdad + caché derivada).

Modelo y servicio (4.1/4.2), kárdex por almacén (4.3), lotes por almacén (4.4), traspasos
reales (4.5), compras→almacén (4.6), reab por almacén (4.7), inventario por almacén (4.8),
GUI (4.9) y equivalencia de stock agregado (4.10). Multiempresa.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import stock_almacen as SA, kardex
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant


def _limpia(db, cod=None, emp=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        if cod:
            for t in ("stock_almacen", "lotes", "movimientos_stock"):
                col = "codigo_articulo"
                cur.execute(f"DELETE FROM {t} WHERE {col}=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
        if emp and emp != EMPRESA_DEFAULT_ID:
            cur.execute("DELETE FROM stock_almacen WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM almacen WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _art(fab, db, stock_central=0, **kw):
    cod = fab.articulo(**kw)
    if stock_central:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET Stock_central=%s WHERE codigo=%s", (stock_central, cod))
            conn.commit()
    fab.al_limpiar(lambda: _limpia(db, cod))
    return cod


def _cache(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central, Stock_total FROM articulos WHERE codigo=%s", (cod,))
        r = cur.fetchone()
        return (r[0], r[1]) if not isinstance(r, dict) else (r["Stock_central"], r["Stock_total"])


def _sum_sa(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(cantidad),0) FROM stock_almacen WHERE codigo_articulo=%s", (cod,))
        r = cur.fetchone()
        return r[0] if not isinstance(r, dict) else list(r.values())[0]


# ── 4.1/4.2 modelo + reseed + equivalencia ───────────────────────────────────
def test_central_por_empresa(db):
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    assert alm["central"] and alm["general"]


def test_reseed_preserva_cache(db, fab):
    cod = _art(fab, db, stock_total=300, stock_central=200, stock_tienda=0)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    assert _sum_sa(db, cod) == 300                  # 200 central + 100 general
    assert _cache(db, cod) == (200, 300)            # caché preservada
    det = {d["tipo_almacen"]: d["cantidad"] for d in SA.obtener_stock_articulo(cod, EMPRESA_DEFAULT_ID)["detalle"]}
    assert det["central"] == 200 and det["logistico"] == 100


def test_incrementar_y_recalcular(db, fab):
    cod = _art(fab, db, stock_total=100, stock_central=100)
    central = SA.almacen_central(EMPRESA_DEFAULT_ID)
    SA.incrementar_stock(cod, central, 50, id_empresa=EMPRESA_DEFAULT_ID)
    assert _cache(db, cod) == (150, 150)            # central y total suben
    assert _sum_sa(db, cod) == 150


def test_decrementar(db, fab):
    cod = _art(fab, db, stock_total=100, stock_central=100)
    central = SA.almacen_central(EMPRESA_DEFAULT_ID)
    SA.decrementar_stock(cod, central, 30, id_empresa=EMPRESA_DEFAULT_ID)
    assert _cache(db, cod) == (70, 70)


# ── 4.5 traspaso real + 4.3 kárdex por almacén ───────────────────────────────
def test_traspaso_real_y_kardex(db, fab):
    cod = _art(fab, db, stock_total=300, stock_central=200)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    ok = SA.traspasar_stock(cod, alm["central"], alm["general"], 50,
                            id_empresa=EMPRESA_DEFAULT_ID, usuario="ana")
    assert ok
    assert SA.obtener_stock_almacen(cod, alm["central"], EMPRESA_DEFAULT_ID) == 150
    assert SA.obtener_stock_almacen(cod, alm["general"], EMPRESA_DEFAULT_ID) == 50 + 100
    assert _sum_sa(db, cod) == 300                  # total global conservado
    mv = kardex.listar_movimientos(codigo=cod, tipo="TRASPASO", id_almacen=alm["central"])
    assert len(mv) == 1 and mv[0]["id_almacen_origen"] == alm["central"]
    assert mv[0]["id_almacen_destino"] == alm["general"]


def test_traspaso_insuficiente(db, fab):
    cod = _art(fab, db, stock_total=10, stock_central=10)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    SA.traspasar_stock(cod, alm["central"], alm["general"], 999, id_empresa=EMPRESA_DEFAULT_ID)
    # origen no queda negativo
    assert SA.obtener_stock_almacen(cod, alm["central"], EMPRESA_DEFAULT_ID) == 0


# ── onboarding: artículo no gestionado no se toca ────────────────────────────
def test_no_gestionado_cache_intacta(db, fab):
    cod = _art(fab, db, stock_total=77, stock_central=40)
    assert SA.esta_gestionado(cod, EMPRESA_DEFAULT_ID) is False
    assert SA.recalcular_cache_articulo(cod, EMPRESA_DEFAULT_ID)   # no-op
    assert _cache(db, cod) == (40, 77)             # caché legada intacta


# ── 4.4 lotes por almacén ─────────────────────────────────────────────────────
def test_lotes_por_almacen(db, fab):
    from src.db import lotes as L
    cod = _art(fab, db)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "LA", 10, id_empresa=EMPRESA_DEFAULT_ID, id_almacen=alm["central"])
    L.registrar_entrada(cod, "LB", 10, id_empresa=EMPRESA_DEFAULT_ID, id_almacen=alm["general"])
    # consumo acotado al almacén central: solo toca LA
    r = L.consumir_fefo(cod, 8, id_empresa=EMPRESA_DEFAULT_ID, id_almacen=alm["central"])
    assert r["consumido"] == 8
    restos = {l["lote"]: l["cantidad"] for l in L.stock_por_lote(cod, id_empresa=EMPRESA_DEFAULT_ID)}
    assert restos.get("LA") == 2 and restos.get("LB") == 10


# ── 4.8 inventario por almacén ────────────────────────────────────────────────
def test_inventario_por_almacen(db, fab):
    from src.db import inventario_fisico as INV
    cod = _art(fab, db, stock_total=100, stock_central=100)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)          # central=100
    iid = INV.crear_inventario("inv alm", id_empresa=EMPRESA_DEFAULT_ID, id_almacen=alm["central"])
    fab.al_limpiar(lambda: _borra_inv(db, iid))
    INV.abrir_inventario(iid, EMPRESA_DEFAULT_ID)
    INV.registrar_recuento(iid, cod, 90, id_empresa=EMPRESA_DEFAULT_ID)   # esperado 100 → -10
    ln = INV.listar_lineas(iid, EMPRESA_DEFAULT_ID)[0]
    assert ln["stock_esperado"] == 100 and ln["diferencia"] == -10
    INV.cerrar_inventario(iid, usuario="ana", id_empresa=EMPRESA_DEFAULT_ID)
    assert SA.obtener_stock_almacen(cod, alm["central"], EMPRESA_DEFAULT_ID) == 90
    mv = kardex.listar_movimientos(codigo=cod, tipo="AJUSTE", id_almacen=alm["central"])
    assert any(m["id_almacen_destino"] == alm["central"] for m in mv)


def _borra_inv(db, iid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM inventarios WHERE id=%s", (iid,))
        conn.commit()


# ── 4.7 reab por almacén ─────────────────────────────────────────────────────
def test_reab_por_almacen(db, fab):
    from src.db import reabastecimiento as R
    cod = _art(fab, db, stock_total=2, stock_central=2)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    R.upsert_config(cod, umbral_min=5, stock_objetivo=20)
    R.set_almacenes_reab(cod, id_almacen_origen=alm["general"], id_almacen_destino=alm["central"])
    props = R.propuestas_por_almacen(alm["central"], id_empresa=EMPRESA_DEFAULT_ID)
    assert any(p["codigo"] == cod for p in props)   # central=2 < umbral 5

    def _borra():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM reab_config WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_borra)


# ── 4.10 equivalencia agregada ───────────────────────────────────────────────
def test_equivalencia_sum(db, fab):
    cod = _art(fab, db, stock_total=500, stock_central=300)
    alm = SA.ensure_almacenes_empresa(EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    SA.incrementar_stock(cod, alm["central"], 100, id_empresa=EMPRESA_DEFAULT_ID)
    SA.traspasar_stock(cod, alm["central"], alm["general"], 40, id_empresa=EMPRESA_DEFAULT_ID)
    central, total = _cache(db, cod)
    # Stock_central == Σ central ; Stock_total == Σ no-tienda == SUM global (sin tiendas)
    assert central == SA.obtener_stock_almacen(cod, alm["central"], EMPRESA_DEFAULT_ID)
    assert total == _sum_sa(db, cod)


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_multiempresa(db, fab):
    # articulos.codigo es PK global → un código por empresa (limitación conocida).
    cod1 = _art(fab, db, stock_total=100, stock_central=100)
    emp2 = fab.empresa("MA B")
    cod2 = "MAB" + uuid.uuid4().hex[:8]
    fab.al_limpiar(lambda: _limpia(db, cod=cod2))
    fab.al_limpiar(lambda: _limpia(db, emp=emp2))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,nombre,Stock_total,Stock_central,id_empresa) "
                    "VALUES (%s,%s,%s,%s,%s)", (cod2, "X", 50, 50, emp2))
        conn.commit()
    SA.reseed_articulo(cod1, EMPRESA_DEFAULT_ID)
    SA.reseed_articulo(cod2, emp2)
    assert SA.stock_total_global(cod1, EMPRESA_DEFAULT_ID) == 100
    assert SA.stock_total_global(cod2, emp2) == 50
    # el almacén central de emp2 no contiene el artículo de la empresa por defecto
    assert SA.stock_total_global(cod1, emp2) == 0


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_gui_stock_almacen(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    cod = _art(fab, db, stock_total=100, stock_central=100)
    SA.reseed_articulo(cod, EMPRESA_DEFAULT_ID)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        from src.gui.stock_almacen_gui import StockAlmacenWindow
        w = StockAlmacenWindow()
        w.in_cod.setText(cod); w._buscar()
        assert w.tabla.rowCount() >= 1
        w.close()
