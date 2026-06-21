"""
VTA.1–VTA.8 · Ventas / TPV / Facturación cliente (cierre de rama).

Clientes PRO, promociones, fidelización, cobros avanzados, venta multialmacén+lote,
presupuestos/pedidos cliente, caja avanzada, facturación comercial + márgenes, multiempresa.
"""

import datetime as _dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import (clientes as CL, promociones as PR, fidelizacion as FID, cobros as CO,
                    ventas_comercial as VC, caja as CAJA, facturas_cliente as FC,
                    stock_almacen as SA, lotes as L)
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _cli(fab, db, **kw):
    cid = CL.crear_cliente(kw.pop("nombre", "Cliente " + uuid.uuid4().hex[:6]), id_empresa=E, **kw)
    fab.al_limpiar(lambda: _del(db, "clientes", "id", cid))
    return cid


def _del(db, tabla, col, val):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s", (val,)); conn.commit()


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "movimientos_stock", "venta_items"):
                c = "codigo_articulo"
                cur.execute(f"DELETE FROM {t} WHERE {c}=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    SA.reseed_articulo(cod, E)
    return cod


# ── VTA.1 clientes ────────────────────────────────────────────────────────────
def test_vta1_clientes_crud_credito(db, fab):
    cid = _cli(fab, db, nif="C1")
    assert CL.actualizar_cliente(cid, id_empresa=E, limite_credito=1000, segmento="oro",
                                 estado_crediticio="normal")
    c = CL.obtener_cliente(cid)
    assert float(c["limite_credito"]) == 1000 and c["segmento"] == "oro"
    assert CL.agregar_contacto(cid, "Juan", cargo="Compras", id_empresa=E)
    assert CL.agregar_direccion(cid, "C/ Mayor 1", tipo="envio", id_empresa=E)
    assert len(CL.listar_contactos(cid, E)) == 1 and len(CL.listar_direcciones(cid, E)) == 1
    assert CL.eliminar_cliente(cid, E) and CL.obtener_cliente(cid)["estado"] == "inactivo"


def test_vta1_segmentacion(db, fab):
    cid = _cli(fab, db); CL.actualizar_cliente(cid, id_empresa=E, segmento="vip")
    assert any(c["id"] == cid for c in CL.listar_clientes(E, segmento="vip"))


# ── VTA.2 promociones ─────────────────────────────────────────────────────────
def test_vta2_promo_pct(db, fab):
    pid = PR.crear_promocion("10% A", tipo="descuento_pct", valor=10,
                             reglas=[{"clave": "codigo", "valor": "ART1"}], id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "promociones", "id_promocion", pid))
    r = PR.evaluar_articulo("ART1", 100, 1, id_empresa=E)
    assert r["descuento"] == 10.0 and r["precio_final"] == 90.0
    r2 = PR.evaluar_articulo("OTRO", 100, 1, id_empresa=E)
    assert r2["descuento"] == 0.0


def test_vta2_promo_2x1_y_temporal(db, fab):
    pid = PR.crear_promocion("2x1 B", tipo="2x1", valor=0,
                             reglas=[{"clave": "codigo", "valor": "ARTB"}], id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "promociones", "id_promocion", pid))
    r = PR.evaluar_articulo("ARTB", 10, 2, id_empresa=E)
    assert r["descuento"] == 10.0   # paga 1 de 2
    # fuera de fecha → no aplica
    ayer = (_dt.date.today() - _dt.timedelta(days=2)).isoformat()
    pid2 = PR.crear_promocion("Caducada", tipo="descuento_pct", valor=50, fecha_fin=ayer,
                              reglas=[{"clave": "codigo", "valor": "ARTB"}], id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "promociones", "id_promocion", pid2))
    r2 = PR.evaluar_articulo("ARTB", 10, 1, id_empresa=E)
    assert r2["descuento"] == 0.0   # 2x1 no aplica a 1 ud y la otra está caducada


# ── VTA.3 fidelización ────────────────────────────────────────────────────────
def test_vta3_puntos_y_cupon(db, fab):
    cid = _cli(fab, db)
    assert FID.acumular_puntos(cid, 50, id_empresa=E) == 50
    assert FID.saldo_puntos(cid, E) == 50
    assert FID.canjear_puntos(cid, 20, E) and FID.saldo_puntos(cid, E) == 30
    assert not FID.canjear_puntos(cid, 999, E)
    FID.revertir_puntos(cid, 50, id_empresa=E)   # devolución
    assert FID.saldo_puntos(cid, E) == 0
    cod_cup = "CUP" + uuid.uuid4().hex[:6]
    cu = FID.emitir_cupon(cod_cup, tipo="descuento_pct", valor=15, id_cliente=cid, id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "cupones", "id", cu))
    assert FID.validar_cupon(cod_cup, E)["valor"] == 15
    assert FID.redimir_cupon(cod_cup, id_empresa=E)
    assert FID.validar_cupon(cod_cup, E) is None   # ya usado


# ── VTA.4 cobros ──────────────────────────────────────────────────────────────
def test_vta4_cobro_mixto_parcial(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 100}])
    fab.al_limpiar(lambda: _del(db, "ventas_cobros", "id_venta", vid))
    CO.registrar_cobro(vid, "efectivo", 60, id_empresa=E)
    CO.registrar_cobro(vid, "tarjeta", 30, id_empresa=E)
    assert CO.total_cobrado(vid, E) == 90.0
    assert CO.saldo_pendiente(vid, 100, E) == 10.0   # parcial/diferido
    d = CO.desglose_por_metodo(E)
    assert d.get("efectivo", 0) >= 60


# ── VTA.5 venta multialmacén/lote ────────────────────────────────────────────
def test_vta5_venta_registra_almacen_lote(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    tid = _min_tienda(db)
    L.registrar_entrada(cod, "LV", 20, id_empresa=E, id_almacen=SA.almacen_de_tienda(tid, E))
    with contexto_tenant(E, tid):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 5, "precio_unitario": 2}])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_almacen, id_lote FROM venta_items WHERE venta_id=%s", (vid,))
        r = cur.fetchone()
    assert r and (r[0] if not isinstance(r, dict) else r["id_almacen"]) is not None


def _min_tienda(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(id) FROM tiendas WHERE id_empresa=%s", (E,))
        r = cur.fetchone()
        return r[0] if not isinstance(r, dict) else list(r.values())[0]


# ── VTA.6 presupuestos/pedidos ───────────────────────────────────────────────
def test_vta6_presupuesto_a_venta(db, fab):
    cod = _art(fab, db, stock_tienda=50); cid = _cli(fab, db)
    pre = VC.crear_presupuesto(id_cliente=cid, lineas=[{"codigo": cod, "cantidad": 3,
                               "precio_unitario": 10}], id_empresa=E)
    assert pre and VC.aprobar_presupuesto(pre, E)
    ped = VC.convertir_a_pedido(pre, id_empresa=E)
    assert ped
    with contexto_tenant(E, None):
        vid = VC.convertir_a_venta(ped, id_empresa=E)
        fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid) if vid else None)
    assert vid
    assert VC.obtener_pedido_cliente(ped, E)["estado"] == "convertido"


# ── VTA.7 caja ────────────────────────────────────────────────────────────────
def test_vta7_caja_sesion_arqueo(db, fab):
    sid = CAJA.abrir_sesion(caja="C1", fondo_inicial=100, id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "caja_sesiones", "id", sid))
    CAJA.registrar_movimiento(sid, "venta", 200, id_empresa=E)
    CAJA.registrar_movimiento(sid, "salida", 50, id_empresa=E)
    a = CAJA.arqueo(sid, E)
    assert a["esperado"] == 250.0   # 100 + 200 - 50
    res = CAJA.cerrar_sesion(sid, 240, id_empresa=E)
    assert res["diferencia"] == -10.0


# ── VTA.8 facturación comercial + márgenes ───────────────────────────────────
def test_vta8_factura_y_cobro(db, fab):
    cid = _cli(fab, db)
    fid = FC.crear_factura(id_cliente=cid, lineas=[{"codigo": "X", "cantidad": 2,
                           "precio_unitario": 50, "coste_unitario": 30}], iva=21, id_empresa=E)
    fab.al_limpiar(lambda: _del(db, "facturas_cliente", "id_factura", fid))
    f = FC.obtener_factura(fid, E)
    assert float(f["total"]) == 121.0 and f["estado"] == "borrador"
    assert FC.emitir(fid, E)
    r = FC.registrar_cobro_factura(fid, 60, E)
    assert r["estado"] == "parcial"
    r2 = FC.registrar_cobro_factura(fid, 61, E)
    assert r2["estado"] == "cobrada"


def test_vta8_margenes(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET coste_medio=4 WHERE codigo=%s", (cod,)); conn.commit()
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 5, "precio_unitario": 10}])
        fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid))
    hoy = _dt.date.today().isoformat()
    m = FC.informe_margenes(desde=hoy, hasta=hoy, id_empresa=E)
    assert m["ventas"] >= 50 and m["margen"] >= 0


# ── Multiempresa ──────────────────────────────────────────────────────────────
def test_vta_multiempresa(db, fab):
    cid = _cli(fab, db, nif="ME1")
    emp2 = fab.empresa("VTA B")
    fab.al_limpiar(lambda: _del(db, "empresas", "id_empresa", emp2))
    assert all(c["id"] != cid for c in CL.listar_clientes(emp2))


# ── GUI ───────────────────────────────────────────────────────────────────────
def test_vta_gui_clientes(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    _cli(fab, db, nombre="GUI Cli")
    with contexto_tenant(E, None):
        from src.gui.clientes_gui import ClientesWindow
        w = ClientesWindow()
        w._buscar()
        assert w.tabla.rowCount() >= 1
        w.close()
