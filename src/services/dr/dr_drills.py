"""
Simulacros automaticos de DR (DR-D).

Tres rutinas idempotentes pensadas para el Scheduler:
  - verify_diario   : verifica el ultimo backup (restore a BD temporal via backup.verificar_backup).
  - restore_test_semanal : crea un snapshot y verifica que es restaurable (drill no destructivo).
  - consistency_mensual  : valida consistencia (BD/replica).
Cada ejecucion se registra en dr_drills y se audita DR_DRILL_OK / DR_DRILL_FAILED.
"""

import logging
from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("dr.drills")


def _registrar(tipo, ok, detalle):
    estado = "ok" if ok else "fallido"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO dr_drills (tipo, estado, detalle) VALUES (%s,%s,%s)",
                        (tipo, estado, (detalle or "")[:255]))
            conn.commit()
    except Exception as e:
        logger.error("registrar drill: %s", e)
    _audit("DR_DRILL_OK" if ok else "DR_DRILL_FAILED", f"{tipo}: {detalle}")
    return {"tipo": tipo, "ok": ok, "detalle": detalle}


def verify_diario() -> dict:
    try:
        from src.db import backup
        r = backup.verificar_backup()
        ok = bool(r and r.get("ok", r.get("resultado") == "ok"))
        return _registrar("verify_diario", ok, str(r))
    except Exception as e:
        return _registrar("verify_diario", False, str(e))


def restore_test_semanal() -> dict:
    try:
        from src.services.dr import dr_pitr
        from src.db import backup
        snap = dr_pitr.crear_snapshot(motivo="drill_restore_test", offsite=False)
        if not snap.get("ok"):
            return _registrar("restore_test_semanal", False, str(snap))
        ver = backup.verificar_backup(snap.get("ruta"))
        ok = bool(ver and ver.get("ok", ver.get("resultado") == "ok"))
        return _registrar("restore_test_semanal", ok, f"snapshot={snap.get('snapshot')} verify={ver}")
    except Exception as e:
        return _registrar("restore_test_semanal", False, str(e))


def consistency_mensual() -> dict:
    try:
        from src.services.dr import dr_replicacion
        r = dr_replicacion.validar_consistencia()
        return _registrar("consistency_mensual", bool(r.get("ok")), str(r))
    except Exception as e:
        return _registrar("consistency_mensual", False, str(e))


def ultimos(tipo=None, limite=50) -> list:
    q = "SELECT * FROM dr_drills"
    p = []
    if tipo:
        q += " WHERE tipo=%s"; p.append(tipo)
    q += " ORDER BY fecha DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("ultimos: %s", e)
        return []


# ── Jobs para el Scheduler (DR_BACKUP_VERIFY_DAILY, etc.) ─────────────────────
def _job_dr_verify(id_empresa):
    return f"drill={verify_diario().get('ok')}"


def _job_dr_restore_test(id_empresa):
    return f"drill={restore_test_semanal().get('ok')}"


def _job_dr_consistency(id_empresa):
    return f"drill={consistency_mensual().get('ok')}"


def registrar_jobs_dr(id_empresa=None):
    """Registra los jobs de DR en el Scheduler (idempotente). Diario/semanal/mensual en horas."""
    from src.services import scheduler
    scheduler.registrar("DR_BACKUP_VERIFY_DAILY", _job_dr_verify)
    scheduler.registrar("DR_RESTORE_TEST_WEEKLY", _job_dr_restore_test)
    scheduler.registrar("DR_CONSISTENCY_CHECK_MONTHLY", _job_dr_consistency)
    scheduler.registrar_job("DR_BACKUP_VERIFY_DAILY", intervalo_horas=24,
                            descripcion="Verificacion diaria de backup", id_empresa=id_empresa)
    scheduler.registrar_job("DR_RESTORE_TEST_WEEKLY", intervalo_horas=168,
                            descripcion="Restore test semanal", id_empresa=id_empresa)
    scheduler.registrar_job("DR_CONSISTENCY_CHECK_MONTHLY", intervalo_horas=720,
                            descripcion="Chequeo de consistencia mensual", id_empresa=id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("dr", accion, "dr_drills", detalle)
    except Exception:
        pass
