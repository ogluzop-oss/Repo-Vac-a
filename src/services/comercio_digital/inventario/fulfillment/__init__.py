"""
PCD · Inventario · Fulfillment Engine (CD-005 · Fase 4). Responde "¿DESDE DÓNDE conviene servir?"
devolviendo un **Plan de Cumplimiento** (objeto de dominio estable, INMUTABLE y VERSIONADO).

Contrato del dominio (ratificado):
  · El Plan de Cumplimiento es el contrato oficial Availability → Fulfillment → Workflow → política
    única de salida. No es un JSON ad hoc: es un objeto de dominio estable (`PlanCumplimiento`).
  · INMUTABLE: nunca se modifica; un cambio de disponibilidad/estrategia/contexto genera un plan
    NUEVO versionado (v2, v3…), preservando la trazabilidad para Audit Replay.
  · Incluye SCORE cuantitativo por alternativa (contrato estable) + origen elegido, alternativas
    descartadas con motivo, ETA, coste, prioridad empresarial y reglas aplicadas.
  · Strategy → Evaluator → Plan (múltiples evaluadores; sin algoritmos rígidos en Fulfillment).
  · Fulfillment consume SOLO capacidades (I9, provider-agnostic): NO importa Rules ni Availability.
  · CONSUME el resultado de Availability (se lo pasan; no lo llama). NO crea reservas (Fase 5). NO
    mueve stock (política única). Workflow EJECUTA el plan; nunca recalcula sourcing.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from src.services.comercio_digital.inventario.fulfillment import evaluadores

FASE = 4
ESTRATEGIA_DEFECTO = "equilibrado"


@dataclass(frozen=True)
class PlanCumplimiento:
    """Objeto de dominio ESTABLE e INMUTABLE (frozen). Contrato entre motores. `version` crece con
    cada replanificación; nunca se muta un plan existente."""
    version: int
    estrategia: str
    codigo: str
    cantidad_solicitada: int
    origen_elegido: dict | None                 # {bucket,ubicacion,cantidad,eta_dias,coste,score}
    asignaciones: tuple                         # parcialidades (Fase 5 completa); Fase 4: 1 principal
    alternativas: tuple                         # [{bucket,...,score,motivo_descarte}]
    reglas_aplicadas: tuple
    pesos: dict
    prioridad_empresarial: str | None
    cubre: bool
    generado_ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return asdict(self)


def _resolver_estrategia(estrategia, id_empresa, contexto):
    """La resolución de estrategia pertenece a la fachada de CAPACIDADES (no a Rules directo).
    Prioridad: explícita > contexto > capacidad (empresa/canal) > defecto. Degradable."""
    if estrategia:
        return estrategia
    if contexto and contexto.get("estrategia"):
        return contexto["estrategia"]
    try:
        from src.platform import capabilities as cap
        rules = cap.rules()
        if rules is not None and hasattr(rules, "estrategia_sourcing"):
            e = rules.estrategia_sourcing(id_empresa=id_empresa)
            if e:
                return e
    except Exception:
        pass
    return ESTRATEGIA_DEFECTO


def _reglas_aplicadas(estrategia, id_empresa, contexto):
    """Reglas aplicadas (para el Plan), consultadas por CAPACIDADES (degradable). Nunca importa Rules."""
    aplicadas = [f"estrategia:{estrategia}"]
    if contexto and contexto.get("prioridad"):
        aplicadas.append(f"prioridad:{contexto['prioridad']}")
    try:
        from src.platform import capabilities as cap
        rules = cap.rules()
        if rules is not None and hasattr(rules, "reglas_sourcing"):
            aplicadas += list(rules.reglas_sourcing(id_empresa=id_empresa) or [])
    except Exception:
        pass
    return tuple(aplicadas)


def _motivo_descarte(alt, elegido) -> str:
    if alt.get("disponible", 0) <= 0:
        return "sin stock"
    if elegido and alt.get("eta_dias", 0) > elegido.get("eta_dias", 0):
        return "ETA mayor"
    if elegido and alt.get("coste", 0) > elegido.get("coste", 0):
        return "coste mayor"
    return "score inferior"


def planificar(disponibilidad, *, estrategia=None, contexto=None, version=1, id_empresa=None) \
        -> PlanCumplimiento:
    """Genera un Plan de Cumplimiento a partir del RESULTADO de Availability (se lo pasan). Elige el
    evaluador por estrategia, puntúa alternativas y produce el plan inmutable. NO reserva, NO mueve
    stock, NO consulta Availability directamente."""
    contexto = contexto or {}
    estrategia = _resolver_estrategia(estrategia, id_empresa, contexto)
    cant = int(disponibilidad.get("cantidad_solicitada", 1) or 1)
    codigo = disponibilidad.get("codigo")

    alternativas = evaluadores.evaluador(estrategia)(disponibilidad, contexto)
    servibles = [a for a in alternativas if a.get("disponible", 0) > 0]

    # Parcialidades multi-origen (Fase 5): se rellena la cantidad desde los mejores orígenes por
    # score hasta cubrir la solicitud. `origen_elegido` = asignación principal (mejor score).
    asignaciones = []
    restante = cant
    usados = set()
    for a in servibles:
        if restante <= 0:
            break
        toma = min(int(a.get("disponible", 0)), restante)
        if toma <= 0:
            continue
        asignaciones.append({"bucket": a["bucket"], "ubicacion": a.get("ubicacion"),
                             "id_tienda": a.get("id_tienda"), "cantidad": toma,
                             "eta_dias": a.get("eta_dias"), "coste": a.get("coste"),
                             "score": a.get("score")})
        usados.add((a["bucket"], a.get("id_tienda")))
        restante -= toma

    asignaciones = tuple(asignaciones)
    elegido = asignaciones[0] if asignaciones else None
    descartadas = tuple({**a, "motivo_descarte": _motivo_descarte(a, elegido)}
                        for a in alternativas if (a["bucket"], a.get("id_tienda")) not in usados)
    cubre = restante <= 0

    return PlanCumplimiento(
        version=int(version), estrategia=estrategia, codigo=codigo, cantidad_solicitada=cant,
        origen_elegido=elegido, asignaciones=asignaciones, alternativas=descartadas,
        reglas_aplicadas=_reglas_aplicadas(estrategia, id_empresa, contexto),
        pesos=evaluadores.pesos(estrategia), prioridad_empresarial=contexto.get("prioridad"),
        cubre=cubre)


def replanificar(plan_previo: PlanCumplimiento, disponibilidad, *, estrategia=None, contexto=None,
                 id_empresa=None) -> PlanCumplimiento:
    """Genera un plan NUEVO (version+1) ante un cambio de disponibilidad/estrategia/contexto. El plan
    anterior permanece INMUTABLE (trazabilidad para Audit Replay)."""
    return planificar(disponibilidad, estrategia=estrategia or plan_previo.estrategia,
                      contexto=contexto, version=plan_previo.version + 1, id_empresa=id_empresa)


def descriptor() -> dict:
    return {"servicio": "cd_fulfillment", "rfc": "CD-005", "fase": FASE, "estado": "implementado",
            "estrategias": evaluadores.estrategias(), "estrategia_defecto": ESTRATEGIA_DEFECTO,
            "plan_inmutable": True, "score_por_alternativa": True, "crea_reservas": False,
            "mueve_stock": False, "conoce_availability": False,
            "contrato": "Strategy → Evaluator → Plan"}


__all__ = ["FASE", "ESTRATEGIA_DEFECTO", "PlanCumplimiento", "planificar", "replanificar",
           "evaluadores", "descriptor"]
