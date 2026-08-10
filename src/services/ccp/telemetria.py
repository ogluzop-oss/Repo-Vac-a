"""
Telemetría/observabilidad de la CCP (Parte J).

Envuelve la infraestructura existente de forma BULLETPROOF (nunca rompe el envío): métricas Prometheus
(`observabilidad.metricas`), trazas OpenTelemetry degradables (`observabilidad.tracing`) y el Event Bus
(`services.eventos`). Preparada para integrarse con Prometheus/OTel ya presentes en el ERP.
"""

import logging

logger = logging.getLogger("ccp.telemetria")


def metrica_envio(canal, estado):
    try:
        from src.services.observabilidad import metricas
        metricas.inc("ccp_comunicaciones_total", etiqueta=f"{canal}:{estado}")
    except Exception:
        pass


def span(nombre, **attrs):
    """Devuelve un context manager de traza (no-op si OTel no está)."""
    try:
        from src.services.observabilidad import tracing
        return tracing.span(nombre, **attrs)
    except Exception:
        from contextlib import nullcontext
        return nullcontext()


def evento(tipo, *, id_empresa=None, com_id=None, canal=None, estado=None, destinatario=None,
           usuario=None):
    try:
        from src.services import eventos as _EV
        _EV.publicar(tipo, id_empresa=id_empresa, usuario=usuario, origen="ccp",
                     ref_entidad="comunicacion", ref_id=com_id,
                     payload={"canal": canal, "estado": estado, "destinatario": destinatario})
    except Exception:
        pass


def auditar(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("ccp", accion, "ccp_comunicaciones", detalle)
    except Exception:
        pass
