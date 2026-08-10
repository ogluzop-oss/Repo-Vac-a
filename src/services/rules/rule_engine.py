"""
Corporate Rules Engine (Fase III · B5) — motor universal SI condiciones ENTONCES acciones.

Evalúa las reglas activas de un evento contra un contexto y ejecuta sus acciones (vía servicios).
Reutiliza el Event Bus (puede suscribirse a eventos) sin lógica de negocio propia. Multiempresa.
API-First (sin PyQt).
"""

import logging

from src.services.rules import conditions as _cond
from src.services.rules import actions as _act
from src.services.rules import rule_registry as _reg

logger = logging.getLogger("rules.engine")

# Reexport CRUD para una API única.
crear_regla = _reg.crear_regla
listar_reglas = _reg.listar_reglas
activar = _reg.activar


def evaluar_evento(evento, contexto=None, *, id_empresa=None) -> dict:
    """Evalúa las reglas del `evento` con `contexto` y ejecuta las acciones de las que se cumplen.
    Devuelve {reglas_evaluadas, disparadas:[{regla, acciones:[...]}]}."""
    reglas = _reg.listar_reglas(id_empresa, evento=evento, solo_activas=True)
    disparadas = []
    for r in reglas:
        if _cond.evaluar(r.get("condiciones") or [], contexto or {}):
            resultados = [_act.ejecutar(a, contexto or {}, id_empresa=id_empresa)
                          for a in (r.get("acciones") or [])]
            disparadas.append({"regla": r.get("nombre"), "id": r.get("id"), "acciones": resultados})
    return {"reglas_evaluadas": len(reglas), "disparadas": disparadas}


def suscribir_al_bus(evento):
    """Conecta el motor a un evento del Event Bus: al publicarse, evalúa sus reglas con el payload."""
    from src.services import eventbus

    def _handler(ev):
        try:
            evaluar_evento(evento, ev.get("payload") or {}, id_empresa=ev.get("id_empresa"))
        except Exception as e:
            logger.debug("handler regla %s: %s", evento, e)

    eventbus.subscribe(evento, _handler)
    return _handler
