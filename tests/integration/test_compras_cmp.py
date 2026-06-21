"""
CMP.1–CMP.8 · Compras y Aprovisionamiento (cierre de rama).

Proveedores profesionales (condiciones/bloqueo/homologación), pedido con almacén+descuento,
recepción avanzada (almacén+lotes+FEFO+kárdex+incidencias), devoluciones a proveedor,
facturación avanzada (abonos/rectificativas/conciliación n:m), costes ampliados (prorrateo +
por almacén), aprovisionamiento/IA (scheduler + lead time proveedor), evaluación, multiempresa.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import compras as C, proveedores as P, stock_almacen as SA, lotes as L, kardex
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "movimientos_stock"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
            conn.commit()
    fab.al_limpiar(_lim)
    SA.reseed_articulo(cod, E)
    return cod


def _prov(fab, db, **kw):
    pid = P.crear_proveedor(kw.pop("razon_social", "Prov " + uuid.uuid4().hex[:6]),
                            id_empresa=E, **kw)

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
            cur.execute("DELETE FROM compras_devoluciones WHERE id_proveedor=%s", (pid,))
            conn.commit()
    fab.al_limpiar(_lim)
    return pid


# ── CMP.1 proveedores ─────────────────────────────────────────────────────────
def test_cmp1_condiciones_y_bloqueo(db, fab):
    pid = _prov(fab, db, cif_nif="B1")
    assert P.actualizar_proveedor(pid, id_empresa=E, descuento=15, lead_time_dias=5, plazo_pago=30)
    c = P.condiciones_comerciales(pid, E)
    assert float(c["descuento"]) == 15 and c["lead_time_dias"] == 5
    assert not P.esta_bloqueado(pid, E)
    P.bloquear(pid, True, E)
    assert P.esta_bloqueado(pid, E)


# ── CMP.2 pedido con almacén + descuento + bloqueo ───────────────────────────
def test_cmp2_pedido_almacen_descuento(db, fab):
    cod = _art(fab, db); central = SA.almacen_central(E)
    pid = _prov(fab, db); P.actualizar_proveedor(pid, id_empresa=E, descuento=10)
    ped = C.crear_pedido(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 10, "precio_unitario": 10}],
                         id_almacen=central, id_empresa=E)
    pd = C.obtener_pedido(ped, E)
    assert pd["id_almacen"] == central and float(pd["total"]) == 90.0   # 100 - 10%


def test_cmp2_proveedor_bloqueado_prohibido(db, fab):
    cod = _art(fab, db); pid = _prov(fab, db); P.bloquear(pid, True, E)
    ped = C.crear_pedido(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 1, "precio_unitario": 1}],
                         id_empresa=E)
    assert ped is None


# ── CMP.3 recepción avanzada ─────────────────────────────────────────────────
def test_cmp3_recepcion_almacen_lote_kardex(db, fab):
    cod = _art(fab, db); central = SA.almacen_central(E); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 20, "precio_unitario": 5}],
                         id_almacen=central, id_empresa=E)
    C.enviar_pedido(ped, E)
    pd = C.obtener_pedido(ped, E)
    rec = C.recibir(ped, [{"id_linea": pd["lineas"][0]["id"], "cantidad": 20, "lote": "LOT1",
                           "fecha_caducidad": "2027-06-01"}], id_empresa=E)
    assert rec["id_almacen"] == central
    assert SA.obtener_stock_almacen(cod, central, E) == 20
    assert L.stock_total_en_lotes(cod, id_empresa=E) == 20
    assert len(kardex.listar_movimientos(codigo=cod, tipo="ENTRADA_COMPRA")) >= 1


def test_cmp3_recepcion_parcial(db, fab):
    cod = _art(fab, db); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 10, "precio_unitario": 2}],
                         id_empresa=E)
    C.enviar_pedido(ped, E); pd = C.obtener_pedido(ped, E)
    C.recibir(ped, [{"id_linea": pd["lineas"][0]["id"], "cantidad": 4}], id_empresa=E)
    assert C.obtener_pedido(ped, E)["estado"] == "PARCIAL"


def test_cmp3_incidencia(db, fab):
    pid = _prov(fab, db)
    iid = C.registrar_incidencia("danado", cantidad=2, id_proveedor=pid, codigo="X", id_empresa=E)
    assert iid and len(C.listar_incidencias(E, id_proveedor=pid)) == 1
    assert C.resolver_incidencia(iid, id_empresa=E)


# ── CMP.4 devoluciones ────────────────────────────────────────────────────────
def test_cmp4_devolucion(db, fab):
    cod = _art(fab, db); central = SA.almacen_central(E); pid = _prov(fab, db)
    SA.incrementar_stock(cod, central, 10, id_empresa=E)
    L.registrar_entrada(cod, "LD", 10, id_empresa=E, id_almacen=central)
    did = C.crear_devolucion(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 3, "lote": "LD",
                             "precio_unitario": 5}], id_almacen=central, id_empresa=E)
    assert did
    assert SA.obtener_stock_almacen(cod, central, E) == 7
    assert L.stock_total_en_lotes(cod, id_empresa=E) == 7
    assert len(kardex.listar_movimientos(codigo=cod, tipo="DEVOLUCION_PROVEEDOR")) == 1


# ── CMP.5 facturación avanzada ───────────────────────────────────────────────
def test_cmp5_abono_y_conciliacion(db, fab):
    cod = _art(fab, db); pid = _prov(fab, db)
    fac = C.registrar_factura(id_proveedor=pid, numero_factura="F1",
                              lineas=[{"codigo": cod, "cantidad": 5, "precio_unitario": 10}],
                              id_empresa=E)
    assert C.obtener_factura(fac, E)["tipo_documento"] == "factura"
    ab = C.registrar_abono(id_proveedor=pid, numero_factura="AB1",
                           lineas=[{"codigo": cod, "cantidad": 2, "precio_unitario": 10}],
                           id_factura_rectificada=fac, id_empresa=E)
    assert C.obtener_factura(ab, E)["tipo_documento"] == "rectificativa"
    # conciliación n:m
    assert C.asociar_recepcion_factura(fac, 999, 50.0, id_empresa=E)
    assert any(r["id_recepcion"] == 999 for r in C.recepciones_de_factura(fac, E))


# ── CMP.6 costes ──────────────────────────────────────────────────────────────
def test_cmp6_prorrateo_y_coste_almacen(db, fab):
    cod = _art(fab, db); central = SA.almacen_central(E); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, lineas=[{"codigo": cod, "cantidad": 10, "precio_unitario": 4}],
                         id_almacen=central, id_empresa=E)
    C.enviar_pedido(ped, E); pd = C.obtener_pedido(ped, E)
    rec = C.recibir(ped, [{"id_linea": pd["lineas"][0]["id"], "cantidad": 10}], id_empresa=E)
    C.registrar_coste_extra("transporte", 50, id_recepcion=rec["id_recepcion"], id_empresa=E)
    pr = C.prorratear_costes_recepcion(rec["id_recepcion"], E)
    assert pr["coste_unitario_extra"] == 5.0          # 50 / 10
    val = C.coste_por_almacen(cod, central, E)
    assert val["cantidad"] == 10 and val["valoracion"] >= 0


# ── CMP.7 aprovisionamiento + IA + scheduler ─────────────────────────────────
def test_cmp7_scheduler(db, fab):
    from src.db import reabastecimiento as R
    cod = _art(fab, db, stock_total=2)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_central=2 WHERE codigo=%s", (cod,)); conn.commit()
    SA.reseed_articulo(cod, E); central = SA.almacen_central(E)
    R.upsert_config(cod, 5, 20, id_empresa=E)
    R.set_parametros_avanzados(cod, stock_maximo=30, punto_pedido=10, id_empresa=E)

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM reab_propuestas WHERE codigo=%s", (cod,))
            cur.execute("DELETE FROM reab_config WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_lim)
    res = R.ejecutar_aprovisionamiento(id_empresa=E, id_almacen=central, usar_ia=False)
    assert len(res["propuestas"]) >= 1


# ── CMP.8 evaluación / homologación ──────────────────────────────────────────
def test_cmp8_evaluacion_homologacion(db, fab):
    pid = _prov(fab, db)
    C.registrar_incidencia("rechazo", cantidad=1, id_proveedor=pid, id_empresa=E)
    k = C.calcular_kpis_proveedor(pid, E)
    assert k["rechazos"] == 1 and 0 <= k["valoracion_global"] <= 100
    assert C.registrar_evaluacion(pid, id_empresa=E)
    assert len(C.listar_evaluaciones(pid, E)) == 1
    assert C.set_homologacion_estado(pid, "aprobado", E)
    assert P.esta_homologado(pid, E)
    assert C.set_homologacion_estado(pid, "bloqueado", E)
    assert P.esta_bloqueado(pid, E)


# ── Multiempresa ──────────────────────────────────────────────────────────────
def test_cmp_multiempresa(db, fab):
    pid1 = _prov(fab, db, cif_nif="ME1")
    emp2 = fab.empresa("CMP B")
    fab.al_limpiar(lambda: _borra_emp(db, emp2))
    pid2 = P.crear_proveedor("Prov B", id_empresa=emp2)
    assert P.obtener_proveedor(pid1, emp2) is None
    assert all(p["id_proveedor"] != pid2 for p in P.listar_proveedores(E))


def _borra_emp(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_cmp_gui(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    with contexto_tenant(E, None):
        from src.gui.compras_avanzado_gui import ComprasAvanzadoWindow
        w = ComprasAvanzadoWindow(usuario={"nombre": "ana", "perfil": "GERENTE"})
        w._carga_dev(); w._carga_inc()
        w.close()
