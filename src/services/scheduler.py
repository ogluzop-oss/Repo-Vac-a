"""
Scheduler empresarial (FASE COM-3).

Unifica las automatizaciones dispersas en jobs registrables, con historial e idempotencia por
intervalo. No introduce un daemon: `ejecutar_pendientes()` se invoca al arrancar/cerrar la app
(como backup_si_corresponde) o desde un proceso externo. Cada job es una función registrada en
REGISTRO; el estado (próxima ejecución, intentos) se persiste. Multiempresa y auditado.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("scheduler")

# Registro en memoria: codigo → callable(id_empresa) -> str|None (detalle).
REGISTRO = {}


def registrar(codigo, fn):
    """Registra el callable de un job (idempotente)."""
    REGISTRO[codigo] = fn


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def registrar_job(codigo, *, intervalo_horas=24, descripcion=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO scheduler_jobs (id_empresa, codigo, descripcion, intervalo_horas) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE descripcion=VALUES(descripcion), "
                        "intervalo_horas=VALUES(intervalo_horas), activo=1",
                        (id_empresa, codigo, descripcion, int(intervalo_horas)))
            conn.commit()
            cur.execute("SELECT id FROM scheduler_jobs WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            r = cur.fetchone()
            return r[0] if not isinstance(r, dict) else list(r.values())[0]
    except Exception as e:
        logger.error("registrar_job: %s", e)
        return None


def cancelar_job(codigo, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE scheduler_jobs SET activo=0 WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cancelar_job: %s", e)
        return False


def _due(cur, id_empresa):
    cur.execute("SELECT codigo, intervalo_horas, proxima_ejecucion FROM scheduler_jobs "
                "WHERE id_empresa=%s AND activo=1", (id_empresa,))
    out = []
    ahora = _dt.datetime.now()
    for r in cur.fetchall():
        d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
        prox = d.get("proxima_ejecucion")
        if prox is None or (isinstance(prox, _dt.datetime) and prox <= ahora):
            out.append(d["codigo"])
    return out


def ejecutar_job(codigo, *, id_empresa=None, intento=1) -> dict:
    """Ejecuta un job registrado, guarda historial y reprograma. Devuelve {estado, detalle}."""
    id_empresa = _emp(id_empresa)
    fn = REGISTRO.get(codigo)
    if not fn:
        return {"estado": "sin_registro", "detalle": codigo}
    estado, detalle = "ok", None
    try:
        detalle = fn(id_empresa)
    except Exception as e:
        estado, detalle = "error", str(e)
        logger.error("ejecutar_job(%s): %s", codigo, e)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT intervalo_horas FROM scheduler_jobs WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            r = cur.fetchone()
            iv = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 24) if r else 24
            prox = _dt.datetime.now() + _dt.timedelta(hours=iv)
            cur.execute("UPDATE scheduler_jobs SET ultima_ejecucion=NOW(), proxima_ejecucion=%s "
                        "WHERE id_empresa=%s AND codigo=%s", (prox, id_empresa, codigo))
            cur.execute("INSERT INTO scheduler_historial (id_empresa, codigo, estado, detalle, intentos) "
                        "VALUES (%s,%s,%s,%s,%s)", (id_empresa, codigo, estado, (detalle or "")[:255], intento))
            conn.commit()
    except Exception as e:
        logger.error("ejecutar_job/persist(%s): %s", codigo, e)
    _audit("AUTOMATIZACION_EJECUTADA", f"{codigo}={estado}")
    return {"estado": estado, "detalle": detalle}


def reintentar_job(codigo, *, id_empresa=None, max_intentos=3) -> dict:
    """Reejecuta un job hasta `max_intentos` mientras devuelva error."""
    res = {"estado": "error"}
    for i in range(1, int(max_intentos) + 1):
        res = ejecutar_job(codigo, id_empresa=id_empresa, intento=i)
        if res.get("estado") == "ok":
            break
    return res


def ejecutar_pendientes(id_empresa=None) -> dict:
    """Ejecuta todos los jobs activos cuya próxima ejecución ha vencido."""
    id_empresa = _emp(id_empresa)
    res = {"ejecutados": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            codigos = _due(cur, id_empresa)
    except Exception as e:
        logger.error("ejecutar_pendientes: %s", e)
        return res
    for c in codigos:
        ejecutar_job(c, id_empresa=id_empresa)
        res["ejecutados"] += 1
    return res


def historial(codigo, id_empresa=None, limite=50) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM scheduler_historial WHERE id_empresa=%s AND codigo=%s "
                        "ORDER BY fecha DESC LIMIT %s", (id_empresa, codigo, int(limite)))
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("historial: %s", e)
        return []


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("scheduler", accion, "scheduler_jobs", detalle)
    except Exception:
        pass


# ── Jobs por defecto (automatizaciones iniciales COM-3) ──────────────────────
def _job_vencimientos(id_empresa):
    from src.db import vencimientos
    n = vencimientos.marcar_vencidos(id_empresa)
    return f"vencimientos marcados={n}"


def _job_workflow_sla(id_empresa):
    from src.services.workflow import workflow_engine
    r = workflow_engine.procesar_sla(id_empresa)
    return f"escaladas={r.get('escaladas')}"


def _job_backup(id_empresa):
    from src.db import backup
    r = backup.backup_si_corresponde(intervalo_horas=24, motivo="programado")
    return "backup ejecutado" if r else "no procede"


def registrar_jobs_por_defecto(id_empresa=None):
    """Registra los callables y crea los jobs por defecto de la empresa (idempotente)."""
    registrar("vencimientos", _job_vencimientos)
    registrar("workflow_sla", _job_workflow_sla)
    registrar("backup", _job_backup)
    registrar_job("vencimientos", intervalo_horas=24, descripcion="Marcar vencimientos vencidos", id_empresa=id_empresa)
    registrar_job("workflow_sla", intervalo_horas=12, descripcion="Escalado SLA de aprobaciones", id_empresa=id_empresa)
    registrar_job("backup", intervalo_horas=24, descripcion="Backup programado", id_empresa=id_empresa)
    # Simulacros de Disaster Recovery (DR-D): verificacion/restore-test/consistencia.
    try:
        from src.services.dr import dr_drills
        dr_drills.registrar_jobs_dr(id_empresa=id_empresa)
    except Exception:
        pass
