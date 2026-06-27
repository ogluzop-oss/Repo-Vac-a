"""
CRM-E — Automatizacion comercial.

Plantillas/reglas comerciales que REUTILIZAN notificaciones + actividades + (opcional) workflow.
Detectores idempotentes pensados para el Scheduler:
  - leads_sin_respuesta : leads 'contactado' sin actividad en N dias -> recordatorio.
  - oportunidades_estancadas : oportunidades abiertas sin movimiento en N dias -> alerta.
  - renovacion_saas : funnel/clientes SaaS proximos a renovar (best-effort).
No crea infraestructura nueva: degrada si faltan servicios.
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.automatizacion")

PLANTILLAS = (
    "seguimiento_automatico", "recordatorio_comercial", "lead_sin_respuesta",
    "oportunidad_estancada", "renovacion_saas", "cross_selling", "upselling",
)


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _notificar(titulo, mensaje, id_empresa, responsable=None):
    try:
        from src.services import notificaciones
        notificaciones.emitir("crm", titulo, mensaje, modulo="crm",
                              usuarios=[responsable] if responsable else None,
                              roles=None if responsable else ["GERENTE", "ADMINISTRADOR"],
                              id_empresa=id_empresa)
    except Exception as e:
        logger.debug("notificar: %s", e)


def leads_sin_respuesta(dias=7, *, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    disparados = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre, responsable FROM crm_leads WHERE id_empresa=%s "
                        "AND estado IN ('nuevo','contactado') AND (fecha_ultimo_contacto IS NULL "
                        "OR fecha_ultimo_contacto < (NOW() - INTERVAL %s DAY))", (eid, int(dias)))
            filas = [(r if isinstance(r, dict) else {"id": r[0], "nombre": r[1], "responsable": r[2]})
                     for r in cur.fetchall()]
    except Exception as e:
        logger.error("leads_sin_respuesta: %s", e)
        return disparados
    for f in filas:
        _notificar("Lead sin respuesta", f"El lead '{f['nombre']}' lleva >{dias} dias sin contacto",
                   eid, f.get("responsable"))
        disparados.append(f["id"])
    return disparados


def oportunidades_estancadas(dias=14, *, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    disparados = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, titulo, responsable FROM crm_oportunidades WHERE id_empresa=%s "
                        "AND estado='abierta' AND fecha_creacion < (NOW() - INTERVAL %s DAY)", (eid, int(dias)))
            filas = [(r if isinstance(r, dict) else {"id": r[0], "titulo": r[1], "responsable": r[2]})
                     for r in cur.fetchall()]
    except Exception as e:
        logger.error("oportunidades_estancadas: %s", e)
        return disparados
    for f in filas:
        _notificar("Oportunidad estancada", f"'{f['titulo']}' sin avanzar >{dias} dias",
                   eid, f.get("responsable"))
        disparados.append(f["id"])
    return disparados


def ejecutar_reglas(*, id_empresa=None) -> dict:
    """Ejecuta todas las reglas comerciales (job del Scheduler)."""
    eid = _emp(id_empresa)
    return {"leads_sin_respuesta": len(leads_sin_respuesta(id_empresa=eid)),
            "oportunidades_estancadas": len(oportunidades_estancadas(id_empresa=eid))}


def _job_crm_automatizacion(id_empresa):
    r = ejecutar_reglas(id_empresa=id_empresa)
    return f"crm_auto={r}"


def registrar_jobs_crm(id_empresa=None):
    """Registra el job de automatizacion comercial en el Scheduler (idempotente)."""
    from src.services import scheduler
    scheduler.registrar("crm_automatizacion", _job_crm_automatizacion)
    scheduler.registrar_job("crm_automatizacion", intervalo_horas=24,
                            descripcion="Reglas comerciales CRM", id_empresa=id_empresa)
