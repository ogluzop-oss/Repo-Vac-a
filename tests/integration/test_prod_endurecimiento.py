"""
PROD M1–M4 · Endurecimiento de producción.

M1 idempotencia contable (cola + asiento), M2 backup (programación/edad), M3 reconciliación
(detección + reparación), M4 política única de salida de stock (sin negativo, con aviso).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _borra_contab(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_apuntes WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


# ── M1 — Idempotencia contable ────────────────────────────────────────────────
def test_m1_encolar_idempotente(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("PRODM1")
    fab.al_limpiar(lambda: _borra_contab(db, emp))
    K.activar(emp, 2026)
    ref = "F" + uuid.uuid4().hex[:8]
    a = Pg.encolar_compra(ref, 121, "2026-03-01", base=100, iva=21, id_empresa=emp)
    b = Pg.encolar_compra(ref, 121, "2026-03-01", base=100, iva=21, id_empresa=emp)
    assert a == b                                   # mismo evento, no se duplica
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_cola WHERE id_empresa=%s AND ref=%s", (emp, ref))
        assert (cur.fetchone()[0]) == 1


def test_m1_procesar_no_duplica_asiento(db, fab):
    from src.services.contabilidad import cuentas as K, posting as Pg
    emp = fab.empresa("PRODM1B")
    fab.al_limpiar(lambda: _borra_contab(db, emp))
    K.activar(emp, 2026)
    ref = "F" + uuid.uuid4().hex[:8]
    Pg.encolar_compra(ref, 121, "2026-03-01", base=100, iva=21, id_empresa=emp)
    Pg.procesar_cola(emp)
    Pg.procesar_cola(emp)                           # reproceso: no debe crear otro asiento
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_asientos WHERE id_empresa=%s AND ref_origen=%s",
                    (emp, f"compra:{ref}"))
        assert (cur.fetchone()[0]) == 1


def test_m1_crear_asiento_idempotente(db, fab):
    from src.services.contabilidad import cuentas as K, asientos as A
    emp = fab.empresa("PRODM1C")
    fab.al_limpiar(lambda: _borra_contab(db, emp))
    K.activar(emp, 2026)
    lineas = [{"codigo_cuenta": "570", "debe": 100}, {"codigo_cuenta": "700", "haber": 100}]
    r1 = A.crear_asiento("2026-03-01", lineas, ref_origen="TEST:1", origen="manual",
                         id_empresa=emp, idempotente=True)
    r2 = A.crear_asiento("2026-03-01", lineas, ref_origen="TEST:1", origen="manual",
                         id_empresa=emp, idempotente=True)
    assert r1 and r2 and r1["id"] == r2["id"]       # no crea un segundo asiento


# ── M2 — Backup ────────────────────────────────────────────────────────────────
def test_m2_backup_programado():
    from src.db import backup
    r = backup.crear_backup(motivo="test_prod")
    assert r["resultado"] == "ok"
    edad = backup.edad_ultimo_backup_horas()
    assert edad is not None and edad < 1
    # con un backup recién hecho, no toca repetir
    assert backup.backup_si_corresponde(intervalo_horas=24) is None


# ── M3 — Reconciliación ───────────────────────────────────────────────────────
def test_m3_detecta_y_repara_divergencia(db, fab):
    from src.db import reconciliacion as R, stock_almacen as SA
    cod = fab.articulo(stock_total=100, stock_tienda=0)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "movimientos_stock"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    SA.reseed_articulo(cod, E)                       # ledger == caché (100 central)
    # Provoca divergencia: cambia la caché por fuera del servicio.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_total=80, Stock_central=80 WHERE codigo=%s", (cod,))
        conn.commit()
    div = [d for d in R.divergencias_stock(E) if d["codigo"] == cod]
    assert div and int(div[0]["cache_total"]) == 80 and int(div[0]["led_total"]) == 100
    # Reparación controlada: reseed desde caché → ledger pasa a 80.
    R.reparar({"divergencias_stock": div, "cola_contable": {"pendientes": 0}}, aplicar=True, id_empresa=E)
    assert SA.stock_total_global(cod, E) == 80


def test_m3_diagnostico_ok(db):
    from src.db import reconciliacion as R
    rep = R.diagnostico(E)
    assert "n_divergencias_stock" in rep and "cola_contable" in rep


# ── M4 — Política única de salida de stock ───────────────────────────────────
def test_m4_no_negativo_con_aviso(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = fab.articulo(stock_tienda=3)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_errores WHERE codigo=%s", (cod,))
            for t in ("stock_almacen", "movimientos_stock", "venta_items"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 5, "precio_unitario": 1}])
    assert vid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s", (cod,))
        assert cur.fetchone()[0] == 0               # nunca negativo (clamp)
        cur.execute("SELECT COUNT(*) FROM ventas_errores WHERE codigo=%s AND motivo LIKE 'sobreventa%%'",
                    (cod,))
        assert cur.fetchone()[0] == 1               # aviso registrado (no silencioso)


def test_m4_venta_normal_sin_aviso(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = fab.articulo(stock_tienda=10)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas_errores WHERE codigo=%s", (cod,))
            for t in ("stock_almacen", "movimientos_stock", "venta_items"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,)); conn.commit()
    fab.al_limpiar(_l)
    with contexto_tenant(E, None):
        registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 4, "precio_unitario": 1}])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s", (cod,))
        assert cur.fetchone()[0] == 6
        cur.execute("SELECT COUNT(*) FROM ventas_errores WHERE codigo=%s", (cod,))
        assert cur.fetchone()[0] == 0               # sin faltante → sin aviso
