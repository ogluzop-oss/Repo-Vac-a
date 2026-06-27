"""
Business Intelligence — DW, motor KPIs, cálculo por dominio (reutilizando servicios),
snapshots, forecasting, dashboard, comparativas multiempresa, exportación y auditoría.
"""

import datetime as dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.bi import kpis as K, snapshots as SN, forecasting as F, dashboard as D, calculadores as C
from src.services.contabilidad import cuentas as Kc

E = EMPRESA_DEFAULT_ID
HOY = "2029-06-15"


@pytest.fixture(autouse=True)
def _defs():
    K.sincronizar_definiciones()
    yield


# ── DW + definiciones ─────────────────────────────────────────────────────────
def test_definiciones(db):
    n = K.sincronizar_definiciones()
    assert n >= 20
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bi_kpi_def WHERE codigo LIKE 'ventas.%'")
        assert cur.fetchone()[0] >= 1


# ── Cálculo + persistencia + idempotencia ────────────────────────────────────
def test_calcular_y_persistir(db):
    cod = "ventas.facturacion"
    try:
        # Inserta una venta para tener facturación real este periodo
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ventas (fecha, total, id_empresa) VALUES (%s,%s,%s)",
                        (f"{HOY} 10:00:00", 250.0, E))
            vid = cur.lastrowid; conn.commit()
        vals = K.calcular_kpi("ventas", periodo="mes", fecha=HOY, id_empresa=E)
        assert vals[cod] >= 250.0
        # recalcular NO duplica fila (upsert idempotente)
        K.calcular_kpi("ventas", periodo="mes", fecha=HOY, id_empresa=E)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bi_kpi_valores WHERE id_empresa=%s AND codigo=%s "
                        "AND periodo='mes'", (E, cod))
            assert cur.fetchone()[0] == 1
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
            cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s AND codigo LIKE %s", (E, "ventas.%"))
            conn.commit()


# ── Reutilización de servicios (tesorería/contabilidad/AEAT no rompen) ───────
def test_calculadores_dominios(db):
    Kc.activar(E)
    for dom in ("ventas", "compras", "inventario", "rrhh", "tesoreria", "contabilidad", "aeat"):
        vals = C.DOMINIOS[dom][0](E, f"{HOY[:4]}-01-01", HOY)
        assert isinstance(vals, dict)        # cada calculador devuelve dict sin lanzar


# ── Snapshot ──────────────────────────────────────────────────────────────────
def test_snapshot(db):
    try:
        r = SN.generar_snapshot("daily", fecha=HOY, id_empresa=E)
        assert r["kpis"] >= 1
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bi_snapshots WHERE id_empresa=%s AND tipo='daily' "
                        "AND fecha_snapshot=%s", (E, HOY))
            assert cur.fetchone()[0] == 1
        SN.generar_snapshot("daily", fecha=HOY, id_empresa=E)   # idempotente
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bi_snapshots WHERE id_empresa=%s AND tipo='daily' "
                        "AND fecha_snapshot=%s", (E, HOY))
            assert cur.fetchone()[0] == 1
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bi_snapshots WHERE id_empresa=%s AND fecha_snapshot=%s", (E, HOY))
            cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s AND periodo='dia'", (E,))
            conn.commit()


# ── Serie histórica + comparar periodos ──────────────────────────────────────
def test_serie_y_comparar(db):
    cod = "tesoreria.disponible"
    try:
        K.guardar_valor(cod, 1000, periodo="mes", fecha="2029-01-01", id_empresa=E)
        K.guardar_valor(cod, 1500, periodo="mes", fecha="2029-02-01", id_empresa=E)
        serie = K.serie_historica(cod, periodo="mes", id_empresa=E)
        assert len(serie) >= 2
        cmp = K.comparar_periodos(cod, "2029-01-01", "2029-02-01", periodo="mes", id_empresa=E)
        assert cmp["a"] == 1000 and cmp["b"] == 1500 and cmp["variacion"] == 500 and cmp["variacion_pct"] == 50.0
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s AND codigo=%s", (E, cod))
            conn.commit()


# ── Forecasting ───────────────────────────────────────────────────────────────
def test_forecasting(db):
    cod = "ventas.facturacion"
    try:
        for i, mes in enumerate(["01", "02", "03", "04", "05", "06"], 1):
            K.guardar_valor(cod, 1000 + i * 100, periodo="mes", fecha=f"2029-{mes}-01", id_empresa=E)
        fc = F.forecast_kpi(cod, periodo="mes", id_empresa=E)
        assert fc["historico"] >= 6 and len(fc["proyecciones"]) == 4
        assert all("valor_estimado" in p for p in fc["proyecciones"])
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s AND codigo=%s", (E, cod))
            conn.commit()


# ── Dashboard + exportación ──────────────────────────────────────────────────
def test_dashboard_export(db):
    d = D.panel(E, periodo="mes", fecha=HOY)
    assert set(["ventas", "tesoreria", "contabilidad", "aeat"]) <= set(d["secciones"].keys())
    js = D.exportar(d, "json"); cs = D.exportar(d, "csv")
    assert '"secciones"' in js
    assert cs.splitlines()[0] == "dominio;codigo;nombre;valor"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s", (E,))
        conn.commit()


# ── Comparativa multiempresa ─────────────────────────────────────────────────
def test_comparativa_multiempresa(db, fab):
    emp2 = fab.empresa("BI B")
    comp = D.comparar_empresas([E, emp2], "tesoreria.disponible", periodo="mes", fecha=HOY)
    assert len(comp) == 2
    assert {c["id_empresa"] for c in comp} == {E, emp2}
    assert all("valor" in c for c in comp)


# ── Auditoría ─────────────────────────────────────────────────────────────────
def test_auditoria(db):
    try:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='BI_KPI_CALCULADO'")
            antes = cur.fetchone()[0]
        K.calcular_kpi("tesoreria", periodo="mes", fecha=HOY, id_empresa=E)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='BI_KPI_CALCULADO'")
            assert cur.fetchone()[0] > antes
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bi_kpi_valores WHERE id_empresa=%s AND periodo='mes'", (E,))
            conn.commit()
