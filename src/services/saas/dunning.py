"""
Dunning — recuperación de impagos (FASE P0.5).

Secuencia por días vencidos desde proximo_cobro: 0 recordatorio · 3 segundo aviso · 7 suspensión
· 15 cancelación. Integrado con notificaciones (y correo best-effort). Idempotente y auditado.
Pensado para ejecutarse como job del Scheduler (registrar_job_dunning).
"""

import datetime as _dt
import logging
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.saas import suscripciones as _S

logger = logging.getLogger("saas.dunning")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _notificar(id_empresa, titulo, mensaje, prioridad="alta"):
    try:
        from src.services import notificaciones
        notificaciones.emitir("saas", titulo, mensaje, modulo="saas", prioridad=prioridad,
                              roles=["ADMINISTRADOR"], id_empresa=id_empresa)
    except Exception:
        pass


def procesar_empresa(id_empresa, *, hoy=None) -> dict:
    """Aplica la secuencia de dunning a UNA empresa según los días vencidos. Devuelve la acción."""
    id_empresa = _emp(id_empresa)
    hoy = hoy or _dt.date.today()
    if isinstance(hoy, str):
        hoy = _dt.datetime.strptime(hoy[:10], "%Y-%m-%d").date()
    s = _S.estado(id_empresa)
    if not s or s.get("estado") in ("cancelada",) or not s.get("proximo_cobro"):
        return {"accion": "ninguna"}
    pc = s["proximo_cobro"]
    pc = pc if isinstance(pc, _dt.date) else _dt.datetime.strptime(str(pc)[:10], "%Y-%m-%d").date()
    vencidos = (hoy - pc).days
    if vencidos < 0:
        return {"accion": "al_dia"}
    if vencidos >= 15:
        _S.cancelar(id_empresa)
        _notificar(id_empresa, "Suscripción cancelada", "Tu suscripción ha sido cancelada por impago.", "critica")
        accion = "cancelada"
    elif vencidos >= 7:
        _S.suspender(id_empresa)
        _notificar(id_empresa, "Suscripción suspendida", "Acceso en modo lectura por impago. Renueva ya.", "critica")
        accion = "suspendida"
    elif vencidos >= 3:
        _notificar(id_empresa, "Segundo aviso de pago", "Tu pago sigue pendiente. Regulariza para evitar la suspensión.")
        accion = "aviso2"
    else:
        _notificar(id_empresa, "Recordatorio de pago", "Tu cuota está pendiente de cobro.")
        accion = "recordatorio"
    _audit(id_empresa, accion, vencidos)
    return {"accion": accion, "vencidos": vencidos}


def procesar_todas(hoy=None) -> dict:
    """Recorre todas las suscripciones con cobro vencido (job del Scheduler)."""
    res = {"procesadas": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT id_empresa FROM suscripciones WHERE estado IN ('activa','suspendida') "
                        "AND proximo_cobro IS NOT NULL AND proximo_cobro < CURDATE()")
            empresas = [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
    except Exception as e:
        logger.error("procesar_todas: %s", e)
        return res
    for emp in empresas:
        procesar_empresa(emp, hoy=hoy); res["procesadas"] += 1
    return res


def registrar_job_dunning(id_empresa=None):
    try:
        from src.services import scheduler as S
        S.registrar("SAAS_DUNNING", lambda emp: f"dunning={procesar_todas()}")
        S.registrar_job("SAAS_DUNNING", intervalo_horas=24, descripcion="Recuperación de impagos SaaS",
                        id_empresa=id_empresa)
    except Exception as e:
        logger.error("registrar_job_dunning: %s", e)


def _audit(id_empresa, accion, vencidos):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "DUNNING", "suscripciones", f"{id_empresa}: {accion} ({vencidos}d)")
    except Exception:
        pass
