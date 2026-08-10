"""
BPD · Bloques (Fase V · Bloque 4). Paleta de bloques del diseñador visual de procesos. Cada bloque
declara su tipo, categoría y cómo se COMPILA hacia la infraestructura existente (Workflow, CCP,
Rules, Scheduler, Event Bus, Documentos). NO define lógica nueva: mapea a servicios existentes.
"""

from __future__ import annotations

# tipo → {categoria, destino (servicio existente que ejecuta el bloque)}
BLOQUES = {
    "inicio": {"categoria": "control", "destino": "workflow"},
    "fin": {"categoria": "control", "destino": "workflow"},
    "condicion": {"categoria": "logica", "destino": "rules"},
    "aprobacion": {"categoria": "workflow", "destino": "workflow.iniciar_proceso"},
    "firma": {"categoria": "documento", "destino": "firma_documental"},
    "enviar_comunicacion": {"categoria": "ccp", "destino": "ccp.enviar_comunicacion"},
    "esperar": {"categoria": "control", "destino": "scheduler"},
    "temporizador": {"categoria": "control", "destino": "scheduler_enterprise.crear_schedule"},
    "webhook": {"categoria": "integracion", "destino": "conectores.webhook"},
    "evento": {"categoria": "eventos", "destino": "eventbus.publish"},
    "script": {"categoria": "avanzado", "destino": "rules.actions"},
    "incidencia": {"categoria": "operacion", "destino": "sat.incidencias"},
    "documento": {"categoria": "documento", "destino": "documental"},
    "workflow_hijo": {"categoria": "workflow", "destino": "workflow.iniciar_proceso"},
    "regla": {"categoria": "logica", "destino": "rules.evaluar"},
}

TIPOS = tuple(BLOQUES.keys())


def paleta() -> list:
    """Paleta para el editor (drag & drop)."""
    return [{"tipo": t, **BLOQUES[t]} for t in TIPOS]


def es_valido(tipo) -> bool:
    return tipo in BLOQUES


def destino(tipo) -> str | None:
    return (BLOQUES.get(tipo) or {}).get("destino")


__all__ = ["BLOQUES", "TIPOS", "paleta", "es_valido", "destino"]
