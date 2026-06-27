"""
Snapshots BI automáticos (FASE BI-11).

Genera y persiste fotos periódicas de los KPIs (bi_kpi_valores) y registra el snapshot en
bi_snapshots (idempotente por empresa+tipo+fecha). Se integra con el Scheduler (rama COM)
mediante jobs BI_SNAPSHOT_DAILY/WEEKLY/MONTHLY/YEARLY.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.services.bi import kpis as _K

logger = logging.getLogger("bi.snapshots")

_PERIODO = {"daily": "dia", "weekly": "semana", "monthly": "mes", "yearly": "anio"}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def generar_snapshot(tipo="daily", *, fecha=None, id_empresa=None) -> dict:
    """Calcula todos los KPIs del periodo y registra el snapshot. Idempotente por (emp,tipo,fecha)."""
    id_empresa = _emp(id_empresa)
    fecha = fecha or _dt.date.today()
    if isinstance(fecha, str):
        fecha = _dt.datetime.strptime(fecha[:10], "%Y-%m-%d").date()
    periodo = _PERIODO.get(tipo, "dia")
    _K.sincronizar_definiciones()
    valores = _K.calcular_todos(periodo=periodo, fecha=fecha, id_empresa=id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bi_snapshots (id_empresa, tipo, fecha_snapshot, kpis, estado) "
                        "VALUES (%s,%s,%s,%s,'ok') ON DUPLICATE KEY UPDATE kpis=VALUES(kpis), estado='ok'",
                        (id_empresa, tipo, fecha.isoformat(), len(valores)))
            conn.commit()
        _audit("BI_SNAPSHOT_GENERADO", f"{tipo} {fecha} ({len(valores)} kpis)")
    except Exception as e:
        logger.error("generar_snapshot: %s", e)
    return {"tipo": tipo, "fecha": fecha.isoformat(), "kpis": len(valores)}


def registrar_jobs_bi(id_empresa=None):
    """Registra en el Scheduler los jobs de snapshot BI (idempotente)."""
    try:
        from src.services import scheduler as S
        S.registrar("BI_SNAPSHOT_DAILY", lambda emp: generar_snapshot("daily", id_empresa=emp) and "ok")
        S.registrar("BI_SNAPSHOT_WEEKLY", lambda emp: generar_snapshot("weekly", id_empresa=emp) and "ok")
        S.registrar("BI_SNAPSHOT_MONTHLY", lambda emp: generar_snapshot("monthly", id_empresa=emp) and "ok")
        S.registrar("BI_SNAPSHOT_YEARLY", lambda emp: generar_snapshot("yearly", id_empresa=emp) and "ok")
        S.registrar_job("BI_SNAPSHOT_DAILY", intervalo_horas=24, descripcion="Snapshot BI diario", id_empresa=id_empresa)
        S.registrar_job("BI_SNAPSHOT_WEEKLY", intervalo_horas=168, descripcion="Snapshot BI semanal", id_empresa=id_empresa)
        S.registrar_job("BI_SNAPSHOT_MONTHLY", intervalo_horas=720, descripcion="Snapshot BI mensual", id_empresa=id_empresa)
        S.registrar_job("BI_SNAPSHOT_YEARLY", intervalo_horas=8760, descripcion="Snapshot BI anual", id_empresa=id_empresa)
    except Exception as e:
        logger.error("registrar_jobs_bi: %s", e)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bi", accion, "bi_snapshots", detalle)
    except Exception:
        pass
