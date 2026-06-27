"""
Alertas técnicas (OBS-5): detecta fallos de subsistema (BD/scheduler/workflow/correo/webhook/
errores masivos API) y emite notificación + auditoría (+ incidente si procede). Degrada sin romper.
"""

import logging
logger = logging.getLogger("obs.alertas")


def _notificar(titulo, mensaje, prioridad="alta", id_empresa=None):
    try:
        from src.services import notificaciones
        notificaciones.emitir("tecnica", titulo, mensaje, modulo="observabilidad",
                              prioridad=prioridad, roles=["ADMINISTRADOR"], id_empresa=id_empresa)
    except Exception:
        pass


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("observabilidad", accion, "alertas_tecnicas", detalle)
    except Exception:
        pass


def emitir(categoria, mensaje, *, severidad="alta", id_empresa=None, crear_incidente=False) -> dict:
    """Emite una alerta técnica. Si crear_incidente, abre un incidente de seguridad."""
    _audit("ALERTA_TECNICA", f"{categoria}: {mensaje}")
    _notificar(f"Alerta técnica: {categoria}", mensaje, "critica" if severidad == "critica" else "alta", id_empresa)
    iid = None
    if crear_incidente:
        try:
            from src.services.seguridad import incidentes
            iid = incidentes.abrir("uso_anomalo", severidad=severidad, detalle=f"{categoria}: {mensaje}",
                                   id_empresa=id_empresa)
        except Exception:
            pass
    try:
        from src.services.observabilidad import metricas
        metricas.inc("sm_alertas_tecnicas_total")
    except Exception:
        pass
    return {"categoria": categoria, "severidad": severidad, "incidente": iid}


def chequear_salud(id_empresa=None) -> dict:
    """Evalúa health() y emite alerta si algún subsistema crítico está caído."""
    from src.services.observabilidad import health
    h = health.health()
    if h.get("status") != "ok":
        caidos = [k for k, v in h.get("subsistemas", {}).items() if v is False]
        if caidos:
            emitir("salud", f"Subsistemas degradados: {', '.join(caidos)}", id_empresa=id_empresa)
    return h
