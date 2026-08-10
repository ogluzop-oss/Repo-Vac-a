"""
Cloud Observability · Alertas (Fase VI · Bloque 12). Alertas para despliegues distribuidos: nodo
caído, nodo lento, latencia alta, y errores de API/Event Bus/Scheduler. Reutiliza el Node Registry
cloud y las alertas técnicas Enterprise (`observabilidad.alertas_tecnicas`). No crea un motor nuevo.
"""

from __future__ import annotations

# Umbrales por defecto (configurables).
UMBRAL_LATENCIA_MS = 500.0
UMBRAL_CARGA = 0.9


def evaluar(*, umbral_latencia=UMBRAL_LATENCIA_MS, umbral_carga=UMBRAL_CARGA) -> list:
    """Devuelve la lista de alertas cloud activas."""
    alertas = []
    from src.platform import cloud
    # Nodos caídos (stale) o en estado degradado/mantenimiento.
    for nombre in cloud.heartbeat.stale():
        alertas.append({"tipo": "nodo_caido", "nivel": "critico", "nodo": nombre})
    for n in cloud.nodes.listar():
        if n.estado == cloud.nodes.DEGRADED:
            alertas.append({"tipo": "nodo_degradado", "nivel": "alto", "nodo": n.nombre})
        if n.latencia_ms > umbral_latencia:
            alertas.append({"tipo": "latencia_alta", "nivel": "alto", "nodo": n.nombre,
                            "latencia_ms": n.latencia_ms})
        if n.carga > umbral_carga:
            alertas.append({"tipo": "nodo_lento", "nivel": "medio", "nodo": n.nombre,
                            "carga": n.carga})
    # Errores de subsistemas (reutiliza alertas técnicas Enterprise si están disponibles).
    try:
        from src.services.observabilidad import alertas_tecnicas
        if hasattr(alertas_tecnicas, "activas"):
            for a in alertas_tecnicas.activas() or []:
                alertas.append({"tipo": "subsistema", "nivel": a.get("nivel", "alto"), "detalle": a})
    except Exception:
        pass
    return alertas


def resumen() -> dict:
    alertas = evaluar()
    return {"total": len(alertas),
            "criticas": len([a for a in alertas if a.get("nivel") == "critico"]),
            "alertas": alertas}


__all__ = ["UMBRAL_LATENCIA_MS", "UMBRAL_CARGA", "evaluar", "resumen"]
