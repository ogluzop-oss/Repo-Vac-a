"""
GMAO-B — Planes de mantenimiento preventivo + tareas + frecuencias.
Frecuencias: diario/semanal/mensual/trimestral/anual/personalizado. Integracion con Scheduler:
un job genera OT preventivas cuando llega proxima_fecha. Multiempresa, auditado.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("gmao.planes")
FRECUENCIAS = {"diario": 1, "semanal": 7, "mensual": 30, "trimestral": 90, "anual": 365, "personalizado": None}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_plan(codigo, nombre, *, id_activo=None, frecuencia="mensual", intervalo_dias=None,
               proxima_fecha=None, tareas=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    dias = intervalo_dias if intervalo_dias else FRECUENCIAS.get(frecuencia) or 30
    proxima_fecha = proxima_fecha or (_dt.date.today() + _dt.timedelta(days=dias))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO planes_mantenimiento (id_empresa, codigo, nombre, id_activo, frecuencia, "
                        "intervalo_dias, proxima_fecha) VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "nombre=VALUES(nombre), frecuencia=VALUES(frecuencia), intervalo_dias=VALUES(intervalo_dias)",
                        (eid, codigo, nombre, id_activo, frecuencia, dias, proxima_fecha))
            cur.execute("SELECT id FROM planes_mantenimiento WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            pid = cur.fetchone()
            pid = pid[0] if not isinstance(pid, dict) else list(pid.values())[0]
            cur.execute("DELETE FROM planes_tareas WHERE id_plan=%s", (pid,))
            for i, t in enumerate(tareas or []):
                cur.execute("INSERT INTO planes_tareas (id_empresa, id_plan, descripcion, orden) "
                            "VALUES (%s,%s,%s,%s)", (eid, pid, t, i))
            conn.commit()
        log_auditoria("gmao", "GMAO_PLAN_CREADO", "planes_mantenimiento", f"plan={pid} {codigo}")
        return pid
    except Exception as e:
        logger.error("crear_plan: %s", e)
        return None


def planes_vencidos(*, id_empresa=None) -> list:
    """Planes activos cuya proxima_fecha <= hoy (deben generar OT preventiva)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM planes_mantenimiento WHERE id_empresa=%s AND activo=1 "
                        "AND proxima_fecha <= CURDATE()", (eid,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("planes_vencidos: %s", e)
        return []


def generar_ot_preventivas(*, id_empresa=None) -> list:
    """Genera una OT preventiva por cada plan vencido y avanza proxima_fecha. Idempotente por fecha."""
    eid = _emp(id_empresa)
    from src.services.gmao import ordenes
    creadas = []
    for plan in planes_vencidos(id_empresa=eid):
        oid = ordenes.crear_ot(tipo="preventiva", id_activo=plan.get("id_activo"), id_plan=plan["id"],
                               descripcion=f"Preventivo: {plan['nombre']}", id_empresa=eid)
        if oid:
            creadas.append(oid)
            # Copia las tareas del plan a la OT.
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("SELECT descripcion FROM planes_tareas WHERE id_plan=%s ORDER BY orden", (plan["id"],))
                    for t in cur.fetchall():
                        d = t[0] if not isinstance(t, dict) else list(t.values())[0]
                        cur.execute("INSERT INTO ot_tareas (id_empresa, id_ot, descripcion) VALUES (%s,%s,%s)",
                                    (eid, oid, d))
                    nueva = _dt.date.today() + _dt.timedelta(days=int(plan.get("intervalo_dias") or 30))
                    cur.execute("UPDATE planes_mantenimiento SET proxima_fecha=%s WHERE id=%s", (nueva, plan["id"]))
                    conn.commit()
            except Exception as e:
                logger.error("copiar tareas plan: %s", e)
    if creadas:
        log_auditoria("gmao", "GMAO_PREVENTIVO_GENERADO", "ordenes_trabajo", f"ots={creadas}")
    return creadas


def listar(*, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM planes_mantenimiento WHERE id_empresa=%s ORDER BY proxima_fecha", (eid,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar planes: %s", e)
        return []


# ── Job Scheduler ─────────────────────────────────────────────────────────────
def _job_preventivo(id_empresa):
    return f"ots_preventivas={len(generar_ot_preventivas(id_empresa=id_empresa))}"


def registrar_jobs_gmao(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("gmao_preventivo", _job_preventivo)
    scheduler.registrar_job("gmao_preventivo", intervalo_horas=24,
                            descripcion="Generar OT preventivas vencidas", id_empresa=id_empresa)
