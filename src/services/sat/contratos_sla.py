"""
SAT-B — Contratos de servicio + SLA (estandar/premium/enterprise). Integra con Workflow:
procesar_sla_tickets marca incumplimientos y escala (reutiliza notificaciones/alertas). Auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.sla")
COBERTURAS = ("estandar", "premium", "enterprise")
# Plazos por defecto por cobertura (horas primera respuesta / resolucion).
DEFAULTS = {"estandar": (24, 72), "premium": (8, 24), "enterprise": (2, 8)}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_sla(codigo, nombre, *, cobertura="estandar", horas_primera_respuesta=None,
              horas_resolucion=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    pr, res = DEFAULTS.get(cobertura, (24, 72))
    horas_primera_respuesta = horas_primera_respuesta or pr
    horas_resolucion = horas_resolucion or res
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO sla_servicio (id_empresa, codigo, nombre, cobertura, "
                        "horas_primera_respuesta, horas_resolucion) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), cobertura=VALUES(cobertura), "
                        "horas_primera_respuesta=VALUES(horas_primera_respuesta), "
                        "horas_resolucion=VALUES(horas_resolucion)",
                        (eid, codigo, nombre, cobertura, horas_primera_respuesta, horas_resolucion))
            cur.execute("SELECT id FROM sla_servicio WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            sid = cur.fetchone()
            conn.commit()
        log_auditoria("sat", "SLA_CREADO", "sla_servicio", f"sla={codigo} {cobertura}")
        return sid[0] if not isinstance(sid, dict) else list(sid.values())[0]
    except Exception as e:
        logger.error("crear_sla: %s", e)
        return None


def crear_contrato(id_cliente, *, cobertura="estandar", id_sla=None, codigo=None,
                   fecha_inicio=None, fecha_fin=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO contratos_servicio (id_empresa, id_cliente, codigo, cobertura, id_sla, "
                        "fecha_inicio, fecha_fin) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_cliente, codigo, cobertura, id_sla, fecha_inicio, fecha_fin))
            cid = cur.lastrowid
            conn.commit()
        log_auditoria("sat", "SLA_CONTRATO", "contratos_servicio", f"contrato={cid} cliente={id_cliente}")
        return cid
    except Exception as e:
        logger.error("crear_contrato: %s", e)
        return None


def procesar_sla_tickets(*, id_empresa=None) -> dict:
    """Marca tickets cuyo SLA de resolucion ha vencido y no estan resueltos/cerrados; escala (notifica)."""
    eid = _emp(id_empresa)
    incumplidos = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, asunto, tecnico FROM tickets WHERE id_empresa=%s AND sla_vencimiento IS NOT NULL "
                        "AND sla_vencimiento < NOW() AND estado NOT IN ('resuelto','cerrado') "
                        "AND sla_incumplido=0", (eid,))
            filas = [(r if isinstance(r, dict) else {"id": r[0], "asunto": r[1], "tecnico": r[2]})
                     for r in cur.fetchall()]
            for f in filas:
                cur.execute("UPDATE tickets SET sla_incumplido=1 WHERE id=%s", (f["id"],))
                incumplidos.append(f["id"])
            conn.commit()
    except Exception as e:
        logger.error("procesar_sla_tickets: %s", e)
        return {"incumplidos": []}
    for f in filas:
        log_auditoria("sat", "SLA_INCUMPLIDO", "tickets", f"ticket={f['id']}")
        _escalar(f, eid)
    return {"incumplidos": incumplidos}


def _escalar(ticket, eid):
    try:
        from src.services import notificaciones
        notificaciones.emitir("sat", f"SLA incumplido ticket {ticket['id']}", ticket.get("asunto", ""),
                              modulo="sat", prioridad="critica", roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
    except Exception:
        pass


def _job_sla(id_empresa):
    return f"sla_incumplidos={len(procesar_sla_tickets(id_empresa=id_empresa).get('incumplidos', []))}"


def registrar_jobs_sat(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("sat_sla", _job_sla)
    scheduler.registrar_job("sat_sla", intervalo_horas=4, descripcion="Control SLA de tickets", id_empresa=id_empresa)
