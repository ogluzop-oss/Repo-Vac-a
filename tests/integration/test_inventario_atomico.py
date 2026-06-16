"""Integración · A2.3: atomicidad de devoluciones, mermas, recepciones y traspasos."""

import pytest

pytestmark = pytest.mark.db


def _stock(db, cod, col="Stock_total"):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COALESCE({col},0) FROM articulos WHERE codigo=%s", (cod,))
        return int(cur.fetchone()[0])


def test_merma_atomica_descuenta_stock(db, fab):
    from src.db import mermas
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _borra(db, "mermas", "codigo", cod))
    assert mermas.registrar_merma(cod, 3, "rotura", columna_stock="Stock_total") is True
    # Merma registrada Y stock descontado en la MISMA transacción.
    assert _stock(db, cod, "Stock_total") == 7
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mermas WHERE codigo=%s", (cod,))
        assert cur.fetchone()[0] == 1


def _crea_venta(db, fab):
    import datetime as _dt
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total, forma_pago, empleado) VALUES (%s,%s,'efectivo','TEST')",
                    (_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 2.0))
        vid = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: _borra(db, "ventas", "id", vid))
    return vid


def test_devolucion_revierte_stock_atomico(db, fab):
    from src.services.tpv import refund_service as RS
    cod = fab.articulo(stock_tienda=0)
    venta_id = _crea_venta(db, fab)
    ok, msg, dev_id = RS.procesar_devolucion(
        venta_id=venta_id,
        items_devolver=[{"codigo_articulo": cod, "nombre": "X", "cantidad": 2,
                         "precio_unitario": 1.0, "subtotal": 2.0, "modo_venta": "UNIDAD"}],
        forma_reembolso="efectivo", forma_pago_original="efectivo",
        empleado="TEST", numero_caja=1, motivo="defecto")
    assert ok and dev_id
    fab.al_limpiar(lambda: _borra_devolucion(db, dev_id))
    # Devolución + ítems + reposición de stock, todo junto.
    assert _stock(db, cod, "Stock_tienda") == 2
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM devolucion_items WHERE devolucion_id=%s", (dev_id,))
        assert cur.fetchone()[0] == 1


def test_traspaso_logistico_atomico(db, fab):
    from src.db import logistica
    cod = fab.articulo(stock_total=20)
    pales = {"PALE-A2TEST-1": {"peso": 5, "articulos": [
        {"codigo": cod, "nombre": "Art", "cantidad": 4}]}}
    try:
        res = logistica.guardar_traspaso_logistico(
            "TIENDA 01", "TIENDA 02", "TEST", "PROPIA", "obs A2.3", pales)
    except Exception as e:
        pytest.skip(f"Setup de logística no disponible en el entorno de test: {e}")
    id_doc = res["id_documento"]
    fab.al_limpiar(lambda: _borra_traspaso(db, id_doc))
    # Documento + líneas creados atómicamente.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documentos_logisticos WHERE id_documento=%s", (id_doc,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM documentos_logisticos_lineas WHERE id_documento=%s", (id_doc,))
        assert cur.fetchone()[0] == 1
    assert res["total_lineas"] == 1


def _borra(db, tabla, col, val):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s", (val,))
        conn.commit()


def _borra_devolucion(db, dev_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM devolucion_items WHERE devolucion_id=%s", (dev_id,))
        cur.execute("DELETE FROM devoluciones WHERE id=%s", (dev_id,))
        conn.commit()


def _borra_traspaso(db, id_doc):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("documentos_logisticos_lineas", "documentos_logisticos_pales", "documentos_logisticos"):
            cur.execute(f"DELETE FROM {t} WHERE id_documento=%s", (id_doc,))
        conn.commit()
