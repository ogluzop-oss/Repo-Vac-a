"""
Health checks (OBS-3): liveness, readiness y health detallado por subsistema.
Reutiliza observabilidad.estado_sistema y comprueba BD/migraciones/scheduler/workflow/correo/saas/backups.
"""

import logging

logger = logging.getLogger("obs.health")


def live() -> dict:
    """Liveness: el proceso responde."""
    return {"status": "ok"}


def _db_ok():
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


def ready() -> dict:
    """Readiness: ¿lista para servir? (BD accesible)."""
    ok = _db_ok()
    return {"status": "ok" if ok else "unavailable", "db": ok}


def _tabla(n):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (n,))
            return cur.fetchone() is not None
    except Exception:
        return False


def health() -> dict:
    """Salud detallada por subsistema."""
    sub = {
        "db": _db_ok(),
        "scheduler": _tabla("scheduler_jobs"),
        "workflow": _tabla("wf_instancias"),
        "correo": _tabla("correos_corporativos"),
        "saas": _tabla("empresa_licencia"),
        "bi": _tabla("bi_kpi_valores"),
    }
    try:
        from src.utils import observabilidad as _obs
        est = _obs.estado_sistema()
        sub["migracion"] = est.get("migracion") if isinstance(est, dict) else None
        sub["backups"] = est.get("backups") if isinstance(est, dict) else None
    except Exception:
        pass
    ok = all(v for k, v in sub.items() if isinstance(v, bool))
    return {"status": "ok" if ok else "degraded", "subsistemas": sub}
