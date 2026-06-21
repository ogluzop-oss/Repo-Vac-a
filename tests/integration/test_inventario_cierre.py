"""
INV.5–INV.8 · Cierre de la rama INVENTARIO.

INV.5 aislamiento multiempresa (reab/config/propuestas), INV.6 reab avanzado (min/max/
punto/lead/IA/compras/multialmacén/multiempresa), INV.7 GUI almacenes, INV.8 equivalencia
E2E (compra/venta/merma/inventario/traspaso → SUM(stock_almacen)==caché), ubicaciones,
mermas, concurrencia (FOR UPDATE) y reseed_todo.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import stock_almacen as SA, reabastecimiento as R
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _limpia(db, cod=None, emp=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        if cod:
            for t in ("stock_almacen", "lotes", "movimientos_stock", "reab_propuestas", "reab_config"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s" if t in
                            ("stock_almacen", "lotes", "movimientos_stock") else
                            f"DELETE FROM {t} WHERE codigo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
        if emp and emp != E:
            for t in ("stock_almacen", "reab_propuestas", "reab_config", "almacen"):
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
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


def _equivale(db, cod):
    """Stock_central==Σcentral y Stock_total==Σno-tienda (caché == ledger)."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central, Stock_total FROM articulos WHERE codigo=%s", (cod,))
        r = cur.fetchone()
        central_c, total_c = (r if not isinstance(r, dict) else (r["Stock_central"], r["Stock_total"]))
        cur.execute("SELECT COALESCE(SUM(CASE WHEN a.tipo_almacen='central' THEN s.cantidad END),0), "
                    "COALESCE(SUM(CASE WHEN a.tipo_almacen<>'tienda' THEN s.cantidad END),0) "
                    "FROM stock_almacen s JOIN almacen a ON a.id=s.id_almacen "
                    "WHERE s.codigo_articulo=%s AND s.id_empresa=%s", (cod, E))
        rr = cur.fetchone()
        central_s, total_s = (rr if not isinstance(rr, dict) else tuple(rr.values()))
    return central_c == central_s and total_c == total_s


# ── INV.5 aislamiento multiempresa ───────────────────────────────────────────
def test_inv5_reab_aislado(db, fab):
    cod = _art(fab, db, stock_total=10)
    emp2 = fab.empresa("CIERRE B")
    cod2 = "CB" + uuid.uuid4().hex[:8]
    fab.al_limpiar(lambda: _limpia(db, cod=cod2))
    fab.al_limpiar(lambda: _limpia(db, emp=emp2))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,nombre,Stock_total,id_empresa) VALUES (%s,%s,%s,%s)",
                    (cod2, "X", 5, emp2)); conn.commit()
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.upsert_config(cod2, 3, 15, id_empresa=emp2)
    a = [c["codigo"] for c in R.listar_config(id_empresa=E)]
    b = [c["codigo"] for c in R.listar_config(id_empresa=emp2)]
    assert cod in a and cod2 not in a
    assert cod2 in b and cod not in b
    assert R.obtener_config(cod2, id_empresa=E) is None      # no fuga entre empresas


def test_inv5_propuestas_aisladas(db, fab):
    cod = _art(fab, db, stock_total=1)
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.crear_propuesta(cod, "X", 19, "ALM", 1, 20, id_empresa=E)
    emp2 = fab.empresa("CIERRE C")
    fab.al_limpiar(lambda: _limpia(db, emp=emp2))
    assert any(p["codigo"] == cod for p in R.listar_propuestas(id_empresa=E))
    assert all(p["codigo"] != cod for p in R.listar_propuestas(id_empresa=emp2))


# ── INV.6 reab avanzado ──────────────────────────────────────────────────────
def test_inv6_motor_min_max_punto(db, fab):
    cod = _art(fab, db, stock_total=5, stock_central=5)
    SA.reseed_articulo(cod, E); central = SA.almacen_central(E)
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.set_parametros_avanzados(cod, stock_maximo=30, punto_pedido=10, lead_time_dias=7, id_empresa=E)
    ids = R.generar_propuestas_almacen(central, id_empresa=E, usar_ia=False)
    assert len(ids) == 1
    p = [x for x in R.listar_propuestas(("pendiente",), id_empresa=E) if x["codigo"] == cod][0]
    assert p["cantidad"] == 25                      # 30 - 5


def test_inv6_no_propone_si_por_encima(db, fab):
    cod = _art(fab, db, stock_total=50, stock_central=50)
    SA.reseed_articulo(cod, E); central = SA.almacen_central(E)
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.set_parametros_avanzados(cod, stock_maximo=30, punto_pedido=10, id_empresa=E)
    assert R.generar_propuestas_almacen(central, id_empresa=E, usar_ia=False) == []


def test_inv6_ia_eleva_punto(db, fab):
    cod = _art(fab, db, stock_total=12, stock_central=12)
    SA.reseed_articulo(cod, E); central = SA.almacen_central(E)
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.set_parametros_avanzados(cod, stock_maximo=40, punto_pedido=10, lead_time_dias=7, id_empresa=E)
    # sin IA: 12 >= punto 10 → no propone
    assert R.generar_propuestas_almacen(central, id_empresa=E, usar_ia=False) == []
    # con IA que prevé 30 de demanda → punto_efectivo=30 > 12 → propone 40-12=28
    ids = R.generar_propuestas_almacen(central, id_empresa=E, usar_ia=True,
                                       prevision_fn=lambda c, d: 30)
    assert len(ids) == 1
    p = [x for x in R.listar_propuestas(("pendiente",), id_empresa=E) if x["codigo"] == cod][0]
    assert p["cantidad"] == 28 and p["stock_actual"] == 12


# ── INV.8.1 equivalencia E2E ─────────────────────────────────────────────────
def test_inv8_equivalencia_compra_venta_merma(db, fab):
    from src.db.conexion import registrar_venta_con_items, modificar_stock_completo
    from src.db.mermas import registrar_merma
    cod = _art(fab, db, stock_total=100, stock_central=100, stock_tienda=0)
    SA.reseed_articulo(cod, E)
    assert _equivale(db, cod)
    central = SA.almacen_central(E)
    SA.incrementar_stock(cod, central, 40, id_empresa=E)         # "compra"
    assert _equivale(db, cod)
    with contexto_tenant(E, None):
        modificar_stock_completo(cod, 0, 120, 20)               # ajuste manual (caché lidera→reseed)
        assert _equivale(db, cod) or SA.esta_gestionado(cod, E)  # gestionado y sincronizado
        registrar_merma(cod, 5, "rotura", columna_stock="Stock_total")
    # tras operaciones legadas el artículo gestionado mantiene equivalencia central/total
    assert _equivale(db, cod)


def test_inv8_equivalencia_traspaso(db, fab):
    cod = _art(fab, db, stock_total=200, stock_central=120)
    SA.reseed_articulo(cod, E)
    alm = SA.ensure_almacenes_empresa(E)
    SA.traspasar_stock(cod, alm["central"], alm["general"], 30, id_empresa=E)
    assert _equivale(db, cod)


# ── INV.8.2 ubicaciones + mermas ─────────────────────────────────────────────
def test_inv8_ubicaciones(db, fab):
    from src.db.conexion import set_ubicacion
    cod = _art(fab, db)
    assert set_ubicacion(cod, "A", "1", "2")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT pasillo, estanteria, balda FROM ubicaciones WHERE codigo_articulo=%s", (cod,))
        r = cur.fetchone()
    assert r is not None


def test_inv8_merma_kardex(db, fab):
    from src.db.mermas import registrar_merma
    from src.db import kardex
    cod = _art(fab, db, stock_total=20)
    fab.al_limpiar(lambda: _borra_mermas(db, cod))
    with contexto_tenant(E, None):
        assert registrar_merma(cod, 3, "caducado", columna_stock="Stock_total")
    assert len(kardex.listar_movimientos(codigo=cod, tipo="MERMA")) == 1


def _borra_mermas(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mermas WHERE codigo=%s", (cod,)); conn.commit()


# ── INV.8.3 concurrencia / FOR UPDATE (consumo no excede existencias) ─────────
def test_inv8_traspaso_no_sobrepasa(db, fab):
    cod = _art(fab, db, stock_total=10, stock_central=10)
    SA.reseed_articulo(cod, E)
    alm = SA.ensure_almacenes_empresa(E)
    # dos traspasos consecutivos de 8 desde central(10): el segundo solo mueve lo disponible
    SA.traspasar_stock(cod, alm["central"], alm["general"], 8, id_empresa=E)
    SA.traspasar_stock(cod, alm["central"], alm["general"], 8, id_empresa=E)
    assert SA.obtener_stock_almacen(cod, alm["central"], E) == 0      # nunca negativo
    assert _equivale(db, cod)


# ── INV.8.4 reseed_todo ──────────────────────────────────────────────────────
def test_inv8_reseed_todo(db, fab):
    cod = _art(fab, db, stock_total=60, stock_central=40)
    n = SA.reseed_todo(E)
    assert n >= 1 and SA.esta_gestionado(cod, E)
    assert SA.stock_total_global(cod, E) == 60


# ── INV.7 GUI almacenes ──────────────────────────────────────────────────────
def test_inv7_gui_almacenes(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    with contexto_tenant(E, None):
        from src.gui.almacenes_gui import AlmacenesWindow
        w = AlmacenesWindow()
        n0 = w.tabla.rowCount()
        cod_alm = "TALM" + uuid.uuid4().hex[:6]
        rid = SA.crear_almacen(f"Almacén {cod_alm}", cod_alm, "regional", id_empresa=E)
        assert rid
        w._cargar()
        assert w.tabla.rowCount() == n0 + 1
        assert SA.actualizar_almacen(rid, id_empresa=E, nombre=f"Almacén {cod_alm} R2")
        assert SA.activar_almacen(rid, activo=False, id_empresa=E)
        w.close()
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM almacen WHERE id=%s", (rid,)); conn.commit()
