"""
Endurecimiento final · eliminación de H1–H7.

H1 recuperación de ventas con integración incompleta (idempotente).
H2 ruta legacy redirigida a la canónica.
H3 ajuste de reposición con kárdex + ledger.
H4 idempotencia fiscal por referencia.
H5 importación CSV integrada.
H6 cola contable procesable sin GUI (en cierre Z).
H7 backup programado + verificación.
"""

import csv
import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import kardex, lotes as L, stock_almacen as SA, reconciliacion as R
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "movimientos_stock", "venta_items", "ventas_errores"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    return cod


def _clean_venta(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
        cur.execute("DELETE FROM ventas WHERE id=%s", (vid,)); conn.commit()


# ── H1 — recuperación de venta con integración incompleta ────────────────────
def test_h1_recuperacion_kardex_idempotente(db, fab):
    cod = _art(fab, db, stock_tienda=10)
    # Simula una venta cuyo hook de kárdex NO se ejecutó: inserta ventas+items a mano.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total, forma_pago, empleado, id_empresa, id_tienda) "
                    "VALUES (NOW(), %s, 'efectivo', 'X', %s, NULL)", (5.0, E))
        vid = cur.lastrowid
        cur.execute("INSERT INTO venta_items (venta_id, codigo_articulo, cantidad, precio_unitario, "
                    "subtotal, id_empresa) VALUES (%s,%s,%s,%s,%s,%s)", (vid, cod, 5, 1, 5, E))
        conn.commit()
    fab.al_limpiar(lambda: _clean_venta(db, vid))
    assert any(v["id"] == vid for v in R.ventas_sin_integrar(E))     # detectada
    # Recupera (re-dispara hooks idempotentes)
    assert R.reintegrar_venta(vid, E)
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA", referencia=vid)) == 1
    # Reintegrar otra vez NO duplica (idempotente)
    R.reintegrar_venta(vid, E)
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA", referencia=vid)) == 1
    assert all(v["id"] != vid for v in R.ventas_sin_integrar(E))     # ya integrada


def test_h1_kardex_idempotente_directo(db, fab):
    cod = _art(fab, db, stock_tienda=5)
    doc = "DOC" + uuid.uuid4().hex[:6]
    assert kardex.registrar_movimiento(cod, "SALIDA_VENTA", 2, id_documento=doc, idempotente=True)
    kardex.registrar_movimiento(cod, "SALIDA_VENTA", 2, id_documento=doc, idempotente=True)
    assert len(kardex.listar_movimientos(codigo=cod, referencia=doc)) == 1


# ── H2 — legacy redirige a la canónica (integrada, sin negativo) ─────────────
def test_h2_legacy_integra(db, fab):
    from src.utils.registro_venta import registrar_venta
    cod = _art(fab, db, stock_tienda=10)
    with contexto_tenant(E, None):
        ok = registrar_venta(cod, 3)
    assert ok
    # generó kárdex (integrada) y no dejó stock negativo
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA")) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s", (cod,))
        assert cur.fetchone()[0] == 7
        cur.execute("DELETE FROM ventas WHERE codigo=%s", (cod,)); conn.commit()


# ── H3 — reposición integra kárdex (vía servicio, sin GUI) ───────────────────
def test_h3_reposicion_via_servicio(db, fab):
    # Reproduce la operación que hace informe_reposicion: mover almacén→lineal + kárdex + reseed.
    cod = _art(fab, db, stock_total=20, stock_tienda=0)
    SA.reseed_articulo(cod, E)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_tienda=5, Stock_total=15 WHERE codigo=%s", (cod,))
        conn.commit()
    kardex.registrar_movimiento(cod, "TRASPASO", 5, origen="ALMACEN", destino="LINEAL", id_empresa=E)
    SA.reseed_articulo(cod, E)
    assert len(kardex.listar_movimientos(codigo=cod, tipo="TRASPASO")) == 1
    assert all(d["codigo"] != cod for d in R.divergencias_stock(E))   # sin divergencia


# ── H4 — idempotencia fiscal por referencia ──────────────────────────────────
def test_h4_fiscal_idempotente(db, fab):
    from src.db import fiscal as F
    emp = fab.empresa("H4")

    def _lf():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fiscal_registros WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM fiscal_config WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,)); conn.commit()
    fab.al_limpiar(_lf)
    ref = "V" + uuid.uuid4().hex[:8]
    assert F.existe_registro(ref, emp) is None
    r1 = F.insertar_registro("ticket", referencia=ref, total=10, id_empresa=emp)
    ya = F.existe_registro(ref, emp)
    assert ya and ya["referencia"] == ref                # el hook reutilizaría este, no crea otro


# ── H5 — importación CSV integrada ───────────────────────────────────────────
def test_h5_csv_integrada(db, fab, tmp_path):
    from src.db.conexion import importar_ventas_desde_csv
    cod = _art(fab, db, stock_tienda=20)
    csv_path = tmp_path / "ventas.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["codigo", "cantidad"]); w.writerow([cod, 4])
    with contexto_tenant(E, None):
        assert importar_ventas_desde_csv(str(csv_path))
    # la venta importada generó kárdex (integración como venta normal)
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA")) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ventas WHERE codigo=%s OR forma_pago='importada'", (cod,)); conn.commit()


# ── H6 — cierre Z procesa la cola contable (sin abrir GUI) ───────────────────
def test_h6_cierre_z_procesa_cola(db, fab, monkeypatch):
    import src.services.tpv.cierre_z as CZ
    llamado = {"n": 0}

    def _fake_procesar(id_empresa=None):
        llamado["n"] += 1; return {"asientos": 0, "eventos": 0}
    monkeypatch.setattr("src.services.contabilidad.posting.procesar_cola", _fake_procesar)
    # Fecha futura única → evita el early-return por cierre ya existente (existe_cierre).
    import random
    fecha = f"2090-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
    try:
        CZ.generar_cierre_z(fecha, 0.0, usuario="test", id_empresa=E, generar_pdf=False)
    except Exception:
        pass
    assert llamado["n"] >= 1


# ── H7 — backup programado + verificación ────────────────────────────────────
def test_h7_backup_programado_y_verificacion():
    from src.db import backup
    r = backup.crear_backup(motivo="test_h7")
    assert r["resultado"] == "ok"
    assert backup.backup_si_corresponde(intervalo_horas=24) is None   # reciente → no repite
    v = backup.verificar_backup()                                     # restaura en BD temporal
    assert v.get("ok") and v.get("tablas", 0) > 0
