"""
Disaster Recovery Enterprise — snapshots/PITR, storage off-site, replicacion, drills, dashboard, runbook.
"""

import datetime as _dt
import os

import pytest

pytestmark = pytest.mark.db


def _limpiar(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dr_snapshots WHERE ruta LIKE %s", ("%test%",))
        cur.execute("DELETE FROM dr_drills WHERE detalle LIKE %s OR tipo LIKE %s", ("%test%", "%verify%"))
        conn.commit()


def test_pitr_snapshot_y_rpo_rto(db):
    from src.services.dr import dr_pitr
    snap = dr_pitr.crear_snapshot(motivo="test_pitr", offsite=True)
    assert snap["ok"] and snap["snapshot"]
    assert dr_pitr.listar_snapshots(limite=1)
    assert dr_pitr.calcular_rpo()["rpo_horas"] is not None
    assert dr_pitr.calcular_rto()["rto_min"] is not None
    # limpieza del fichero de backup generado
    if snap.get("ruta") and os.path.exists(snap["ruta"]):
        os.remove(snap["ruta"])
        j = snap["ruta"][:-4] + ".json"
        if os.path.exists(j):
            os.remove(j)


def test_pitr_restore_timestamp(db):
    from src.services.dr import dr_pitr
    snap = dr_pitr.crear_snapshot(motivo="test_pitr_restore", offsite=False)
    assert snap["ok"]
    # +2s de margen: evita el clock-skew entre el servidor de BD (creado_en = NOW() del
    # servidor) y el reloj local, que hacía este test flaky en CI. La feature restaura a
    # un instante >= creación; en producción siempre se restaura a tiempos pasados.
    r = dr_pitr.restaurar_a_timestamp(_dt.datetime.now() + _dt.timedelta(seconds=2))
    assert r["ok"]
    # snapshot anterior a una fecha muy antigua -> no hay
    r2 = dr_pitr.restaurar_a_timestamp(_dt.datetime(2000, 1, 1))
    assert r2["ok"] is False
    if snap.get("ruta") and os.path.exists(snap["ruta"]):
        os.remove(snap["ruta"])


def test_storage_backends():
    from src.services.dr import dr_storage
    assert dr_storage.backend("local").codigo == "local"
    # backends remotos declarados pero no configurados -> no rompen
    for cod in ("s3", "azure", "gcs", "object"):
        b = dr_storage.backend(cod)
        assert b.codigo == cod
        assert b.subir("/inexistente")["ok"] is False


def test_replicacion_degradable():
    from src.services.dr import dr_replicacion
    est = dr_replicacion.estado_replicacion()
    assert est["estado"] in ("no_configurada", "configurada")
    assert dr_replicacion.validar_consistencia()["ok"] is True


def test_drills(db):
    from src.services.dr import dr_drills
    r = dr_drills.verify_diario()
    assert "ok" in r
    assert dr_drills.ultimos("verify_diario", 1)


def test_dashboard_y_runbook(db):
    from src.services.dr import dr_dashboard
    p = dr_dashboard.panel()
    assert {"rpo", "rto", "replicacion", "almacenamiento"} <= set(p.keys())
    for fmt in ("json", "html"):
        rb = dr_dashboard.runbook(fmt)
        assert rb["ok"] and os.path.exists(rb["ruta"])
        os.remove(rb["ruta"])


def test_jobs_dr_registrables():
    """Los jobs DR se registran como callables sin lanzar."""
    from src.services import scheduler
    from src.services.dr import dr_drills
    dr_drills.registrar_jobs_dr()
    assert "DR_BACKUP_VERIFY_DAILY" in scheduler.REGISTRO
