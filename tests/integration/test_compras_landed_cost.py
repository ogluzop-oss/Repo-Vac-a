"""Fase B — Landed Cost.

Prorrateo de costes indirectos (transporte/aduanas/seguro/…) sobre las líneas recibidas, por
componente × línea (auditable, `compras_costes_extra_lineas`), con recalculo de
`articulos.coste_medio`/`coste_actual` y del snapshot en `lotes` — vía A (compras) y vía B2B
(Smart Suppliers, `transaccion_lineas`). Incluye el cierre del bug prerrequisito: la recepción B2B
(`b2b_pedidos.recibir_mercancia`) ahora SÍ actualiza `coste_medio` nada más recibir la mercancía.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import compras as C, proveedores as P, stock_almacen as SA
from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


def _art(fab, db, peso_unitario=None, **kw):
    cod = fab.articulo(**kw)
    if peso_unitario is not None:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET peso_unitario=%s WHERE codigo=%s AND id_empresa=%s",
                        (peso_unitario, cod, E))
            conn.commit()

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "lotes_movimientos", "movimientos_stock"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
            conn.commit()
    fab.al_limpiar(_lim)
    SA.reseed_articulo(cod, E)
    return cod


def _prov(fab, db, **kw):
    pid = P.crear_proveedor("Prov Landed " + uuid.uuid4().hex[:6], id_empresa=E, **kw)

    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
            conn.commit()
    fab.al_limpiar(_lim)
    return pid


def _limpiar_pedido(fab, db, id_pedido):
    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_recepcion FROM compras_recepciones WHERE id_pedido=%s", (id_pedido,))
            recs = [r[0] if not isinstance(r, dict) else r["id_recepcion"] for r in cur.fetchall()]
            for rid in recs:
                cur.execute("DELETE FROM compras_costes_extra_lineas WHERE id_recepcion=%s", (rid,))
            cur.execute("DELETE FROM compras_costes_extra WHERE id_recepcion IN "
                        "(SELECT id_recepcion FROM compras_recepciones WHERE id_pedido=%s)", (id_pedido,))
            cur.execute("DELETE FROM compras_recepciones_lineas WHERE id_recepcion IN "
                        "(SELECT id_recepcion FROM compras_recepciones WHERE id_pedido=%s)", (id_pedido,))
            cur.execute("DELETE FROM compras_recepciones WHERE id_pedido=%s", (id_pedido,))
            cur.execute("DELETE FROM compras_pedidos_lineas WHERE id_pedido=%s", (id_pedido,))
            cur.execute("DELETE FROM compras_pedidos WHERE id_pedido=%s", (id_pedido,))
            conn.commit()
    fab.al_limpiar(_lim)


def _limpiar_tx(fab, db, id_tx):
    def _lim():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM compras_costes_extra_lineas WHERE id_coste_extra IN "
                        "(SELECT id FROM compras_costes_extra WHERE id_tx=%s)", (id_tx,))
            cur.execute("DELETE FROM compras_costes_extra WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_lineas WHERE id_tx=%s", (id_tx,))
            cur.execute("DELETE FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
            conn.commit()
    fab.al_limpiar(_lim)


# ── Vía A (compras): reparto por VALOR, 2 líneas ─────────────────────────────
def test_landed_valor_dos_lineas(db, fab):
    codA = _art(fab, db); codB = _art(fab, db)
    central = SA.almacen_central(E); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, id_almacen=central, id_empresa=E, lineas=[
        {"codigo": codA, "cantidad": 10, "precio_unitario": 4},
        {"codigo": codB, "cantidad": 5, "precio_unitario": 8}])
    _limpiar_pedido(fab, db, ped)
    C.enviar_pedido(ped, E)
    pd = C.obtener_pedido(ped, E)
    lA = next(l for l in pd["lineas"] if l["codigo_articulo"] == codA)
    lB = next(l for l in pd["lineas"] if l["codigo_articulo"] == codB)
    rec = C.recibir(ped, [{"id_linea": lA["id"], "cantidad": 10, "lote": "LA"},
                          {"id_linea": lB["id"], "cantidad": 5, "lote": "LB"}], id_empresa=E)
    assert C.obtener_costes(codA)["coste_medio"] == 4.0
    assert C.obtener_costes(codB)["coste_medio"] == 8.0

    id_transporte = C.registrar_coste_extra("transporte", 24, id_recepcion=rec["id_recepcion"],
                                            id_empresa=E, metodo_prorrateo="valor")
    id_seguro = C.registrar_coste_extra("seguro", 16, id_recepcion=rec["id_recepcion"],
                                        id_empresa=E, metodo_prorrateo="valor")

    res = C.prorratear_costes_recepcion(id_recepcion=rec["id_recepcion"], id_empresa=E)
    assert res["ok"] is True
    assert res["metodo"] == "valor"
    assert res["total_distribuido"] == 40.0
    # valor A = 10*4=40, valor B = 5*8=40 -> reparto 50/50 en ambos componentes
    assert res["por_articulo"][codA] == {"cantidad": 10, "coste_base": 4.0, "coste_indirecto": 2.0,
                                         "coste_landed": 6.0}
    assert res["por_articulo"][codB] == {"cantidad": 5, "coste_base": 8.0, "coste_indirecto": 4.0,
                                         "coste_landed": 12.0}
    # landed reemplaza (no acumula) la PMP base ya escrita por recibir().
    assert C.obtener_costes(codA)["coste_medio"] == 6.0
    assert C.obtener_costes(codB)["coste_medio"] == 12.0

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT coste_unitario_base, coste_unitario_indirecto, coste_unitario_landed "
                    "FROM lotes WHERE codigo_articulo=%s AND id_empresa=%s", (codA, E))
        row = cur.fetchone()
        vals = list(row.values()) if isinstance(row, dict) else list(row)
    assert [float(v) for v in vals] == [4.0, 2.0, 6.0]

    # Auditoría: importe_asignado de cada componente suma EXACTO su importe original.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_coste_extra, SUM(importe_asignado) FROM compras_costes_extra_lineas "
                    "WHERE id_recepcion=%s GROUP BY id_coste_extra", (rec["id_recepcion"],))
        sumas = {}
        for r in cur.fetchall():
            k, v = (r["id_coste_extra"], r["SUM(importe_asignado)"]) if isinstance(r, dict) else (r[0], r[1])
            sumas[k] = float(v)
    assert sumas[id_transporte] == 24.0
    assert sumas[id_seguro] == 16.0

    # Idempotencia: reejecutar sin componentes nuevos no toca nada.
    res2 = C.prorratear_costes_recepcion(id_recepcion=rec["id_recepcion"], id_empresa=E)
    assert res2 == {"ok": True, "prorrateado": 0.0, "componentes": 0, "lineas": 0,
                    "total_distribuido": 0.0, "por_articulo": {}}


# ── Vía A (compras): reparto por PESO con fallback a cantidad ───────────────
def test_landed_peso_con_fallback(db, fab):
    codC = _art(fab, db, peso_unitario=2.0)     # CON peso_unitario
    codD = _art(fab, db, peso_unitario=None)    # SIN peso_unitario -> fallback a cantidad
    central = SA.almacen_central(E); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, id_almacen=central, id_empresa=E, lineas=[
        {"codigo": codC, "cantidad": 10, "precio_unitario": 5},
        {"codigo": codD, "cantidad": 4, "precio_unitario": 3}])
    _limpiar_pedido(fab, db, ped)
    C.enviar_pedido(ped, E)
    pd = C.obtener_pedido(ped, E)
    lC = next(l for l in pd["lineas"] if l["codigo_articulo"] == codC)
    lD = next(l for l in pd["lineas"] if l["codigo_articulo"] == codD)
    rec = C.recibir(ped, [{"id_linea": lC["id"], "cantidad": 10, "lote": "LC"},
                          {"id_linea": lD["id"], "cantidad": 4, "lote": "LD"}], id_empresa=E)
    C.registrar_coste_extra("manipulacion", 48, id_recepcion=rec["id_recepcion"], id_empresa=E,
                            metodo_prorrateo="peso")
    res = C.prorratear_costes_recepcion(id_recepcion=rec["id_recepcion"], id_empresa=E)
    assert res["ok"] is True and res["metodo"] == "peso"
    # peso C = 10*2.0 = 20 ; peso D (fallback) = 4 ; total = 24
    # 48 * 20/24 = 40 -> C indirecto/ud = 4.0 ; resto 8 -> D indirecto/ud = 2.0
    assert res["por_articulo"][codC] == {"cantidad": 10, "coste_base": 5.0, "coste_indirecto": 4.0,
                                         "coste_landed": 9.0}
    assert res["por_articulo"][codD] == {"cantidad": 4, "coste_base": 3.0, "coste_indirecto": 2.0,
                                         "coste_landed": 5.0}
    assert C.obtener_costes(codC)["coste_medio"] == 9.0
    assert C.obtener_costes(codD)["coste_medio"] == 5.0

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT metodo_usado FROM compras_costes_extra_lineas WHERE id_recepcion=%s "
                    "AND codigo_articulo=%s", (rec["id_recepcion"], codD))
        fila = cur.fetchone()
        metodo_usado = fila["metodo_usado"] if isinstance(fila, dict) else fila[0]
    assert metodo_usado == "cantidad"   # fallback honesto: D no tenía peso_unitario


def test_landed_metodos_mixtos_sin_metodo_explicito_falla(db, fab):
    cod = _art(fab, db)
    central = SA.almacen_central(E); pid = _prov(fab, db)
    ped = C.crear_pedido(id_proveedor=pid, id_almacen=central, id_empresa=E,
                         lineas=[{"codigo": cod, "cantidad": 5, "precio_unitario": 2}])
    _limpiar_pedido(fab, db, ped)
    C.enviar_pedido(ped, E)
    pd = C.obtener_pedido(ped, E)
    rec = C.recibir(ped, [{"id_linea": pd["lineas"][0]["id"], "cantidad": 5}], id_empresa=E)
    C.registrar_coste_extra("transporte", 10, id_recepcion=rec["id_recepcion"], id_empresa=E,
                            metodo_prorrateo="valor")
    C.registrar_coste_extra("seguro", 5, id_recepcion=rec["id_recepcion"], id_empresa=E,
                            metodo_prorrateo="peso")
    # `prorratear_costes_recepcion` nunca lanza (mismo criterio catch-all que la versión anterior
    # de la función): la ambigüedad se reporta como {"ok": False, "error": ...}.
    res = C.prorratear_costes_recepcion(id_recepcion=rec["id_recepcion"], id_empresa=E)
    assert res["ok"] is False
    assert "metodo_prorrateo distintos" in res["error"]
    # Con `metodo=` explícito sí funciona (desambigua).
    res2 = C.prorratear_costes_recepcion(id_recepcion=rec["id_recepcion"], id_empresa=E, metodo="cantidad")
    assert res2["ok"] is True and res2["metodo"] == "cantidad"


# ── Vía B2B: cierre del bug prerrequisito + landed cost ──────────────────────
def test_landed_b2b_recibir_actualiza_pmp_y_prorratea(db, fab):
    from src.services.comercio_digital import transacciones as TX
    from src.services.compras import b2b_pedidos as B2B

    cod = _art(fab, db)
    assert C.obtener_costes(cod).get("coste_medio", 0) in (0, 0.0, None)

    id_tx = TX.crear(tipo="pedido", origen="b2b", estado="BORRADOR", id_empresa=E,
                     lineas=[{"codigo": cod, "nombre": "Art B2B Landed", "cantidad": 6,
                             "precio_unitario": 10.0}])
    assert id_tx
    _limpiar_tx(fab, db, id_tx)
    tr = TX.transicionar(id_tx, "CONFIRMADA", actor="test", id_empresa=E)
    assert tr["ok"] is True

    r = B2B.recibir_mercancia(id_tx, actor="test", id_empresa=E)
    assert r["ok"] is True
    # *** Cierre del bug prerrequisito: la recepción B2B ahora SÍ actualiza coste_medio. ***
    assert C.obtener_costes(cod)["coste_medio"] == 10.0

    id_ce = C.registrar_coste_extra("transporte", 12, id_tx=id_tx, id_empresa=E,
                                    metodo_prorrateo="cantidad")
    assert id_ce
    res = C.prorratear_costes_recepcion(id_tx=id_tx, id_empresa=E)
    assert res["ok"] is True
    assert res["por_articulo"][cod] == {"cantidad": 6, "coste_base": 10.0, "coste_indirecto": 2.0,
                                        "coste_landed": 12.0}
    assert C.obtener_costes(cod)["coste_medio"] == 12.0

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_recepcion, cantidad, importe_asignado FROM "
                    "compras_costes_extra_lineas WHERE id_coste_extra=%s", (id_ce,))
        fila = cur.fetchone()
        id_recepcion, cantidad, importe = (list(fila.values()) if isinstance(fila, dict) else list(fila))
    assert id_recepcion is None       # B2B: sin fila en compras_recepciones
    assert int(cantidad) == 6
    assert float(importe) == 12.0


def test_landed_registrar_coste_extra_validaciones(db, fab):
    with pytest.raises(ValueError):
        C.registrar_coste_extra("otros", 1, id_empresa=E)            # ni id_recepcion ni id_tx
    with pytest.raises(ValueError):
        C.registrar_coste_extra("otros", 1, id_recepcion=1, id_tx="x", id_empresa=E)  # ambos
    with pytest.raises(ValueError):
        C.registrar_coste_extra("otros", 1, id_recepcion=1, id_empresa=E,
                                metodo_prorrateo="no_valido")
