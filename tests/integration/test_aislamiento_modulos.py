"""Integración · A4.1: barrida de aislamiento multi-tenant de tablas transaccionales.

Usa `empresa.contexto_tenant` (override por hilo) para crear datos como empresa B y
verifica que NO son visibles desde la empresa A (por defecto)."""

import pytest

pytestmark = pytest.mark.db


def _venta_items_emp(db, venta_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_empresa FROM ventas WHERE id=%s", (venta_id,))
        emp_v = cur.fetchone()[0]
        cur.execute("SELECT id_empresa FROM venta_items WHERE venta_id=%s LIMIT 1", (venta_id,))
        r = cur.fetchone()
        return emp_v, (r[0] if r else None)


def test_ventas_etiquetadas_por_tenant(db, fab):
    from src.db import conexion
    from src.db.empresa import contexto_tenant
    emp_b = fab.empresa("AISL VENTAS B")
    cod = fab.articulo(stock_total=10)
    with contexto_tenant(emp_b, None):
        vid = conexion.registrar_venta_con_items(
            items=[{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 2.0}],
            forma_pago="efectivo")
    fab.al_limpiar(lambda: _borra_venta(db, vid))
    emp_v, emp_i = _venta_items_emp(db, vid)
    # La venta y sus ítems quedan etiquetados con la empresa B (no el default).
    assert emp_v == emp_b and emp_i == emp_b


def test_buscar_ventas_aislada(db, fab):
    from src.db import conexion
    from src.db import ventas_busqueda as VB
    from src.db.empresa import contexto_tenant
    emp_b = fab.empresa("AISL BUSCAR B")
    cod = fab.articulo(stock_total=10)
    with contexto_tenant(emp_b, None):
        vid = conexion.registrar_venta_con_items(
            items=[{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 5.0}],
            forma_pago="efectivo")
    fab.al_limpiar(lambda: _borra_venta(db, vid))
    # Desde la empresa por defecto (A) no debe aparecer la venta de B.
    ids_a = {v.get("id") or v.get("venta_id") for v in VB.buscar_ventas(limite=2000)}
    ids_b = {v.get("id") or v.get("venta_id") for v in VB.buscar_ventas(limite=2000, id_empresa=emp_b)}
    assert vid in ids_b and vid not in ids_a


def test_mermas_aisladas(db, fab):
    from src.db import mermas
    from src.db.empresa import contexto_tenant
    emp_b = fab.empresa("AISL MERMAS B")
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _borra(db, "mermas", "codigo", cod))
    with contexto_tenant(emp_b, None):
        assert mermas.registrar_merma(cod, 1, "rotura test")
        vis_b = {m[1] for m in mermas.obtener_mermas()}   # obtener_mermas → tuplas (codigo=idx 1)
    vis_a = {m[1] for m in mermas.obtener_mermas()}      # empresa por defecto
    assert cod in vis_b and cod not in vis_a


def test_documentos_aislados(db, fab):
    from src.db import documentos as D
    from src.db.empresa import contexto_tenant
    emp_b = fab.empresa("AISL DOCS B")
    ref = "A4REF-" + emp_b[:8]
    fab.al_limpiar(lambda: _borra(db, "documentos_registro", "referencia", ref))
    with contexto_tenant(emp_b, None):
        D.registrar_documento("documentos/_a4_test.pdf", tipo="otros", referencia=ref)
    # listar_documentos aísla cuando el llamador pasa la empresa (patrón del centro
    # documental). Vista de A (empresa por defecto) vs vista de B.
    refs_a = {d.get("referencia") for d in D.listar_documentos(limite=5000, id_empresa=db.EMPRESA_DEFAULT_ID)}
    refs_b = {d.get("referencia") for d in D.listar_documentos(limite=5000, id_empresa=emp_b)}
    assert ref in refs_b and ref not in refs_a


def _borra(db, tabla, col, val):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s", (val,))
        conn.commit()


def _borra_venta(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
        cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
        conn.commit()
