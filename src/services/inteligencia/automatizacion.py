"""
Etapa C · Fase C2 — Automatización Empresarial (capa transversal).

Puente que conecta EVENTOS/condiciones de dominio con PROPUESTAS del Centro de Decisiones y con los
circuitos de Workflow. NO es un segundo Scheduler/Workflow/Rules/Event Bus: los REUTILIZA por
capacidades. Las automatizaciones NUNCA ejecutan cambios de negocio: siempre PROPONEN (decisión +
workflow sugerido) para decisión humana. Multiempresa. Degradable. Auditable (reutiliza el ledger
`decisiones_ia` y el Event Bus).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("inteligencia.automatizacion")

FASE = "C2"

# Registro de reglas de automatización: disparador lógico → [funciones]. Cada función recibe
# (payload, id_empresa) y devuelve un dict de propuesta (o None). Pluggable.
_REGLAS: dict = {}


def registrar_regla(disparador, fn):
    """Registra una regla de automatización reactiva para un disparador lógico."""
    _REGLAS.setdefault(disparador, []).append(fn)
    return disparador


def disparadores():
    return sorted(_REGLAS)


# ── Reglas incorporadas (ejemplos del Prompt Maestro; solo PROPONEN) ──────────
def _r_stock_bajo(payload, id_empresa):
    cod = (payload or {}).get("codigo")
    return {"dominio": "compras", "tipo": "recomendacion", "titulo": "Crear propuesta de compra",
            "descripcion": f"Stock bajo de {cod}; conviene reponer" if cod else "Stock bajo detectado",
            "entidad": "articulo", "entidad_ref": cod, "prioridad": "ALTA",
            "workflow": "compras_pedido", "datos": payload}


def _r_mercancia_recibida(payload, id_empresa):
    cod = (payload or {}).get("codigo")
    return {"dominio": "inventario", "tipo": "recomendacion", "titulo": "Revisar disponibilidad",
            "descripcion": f"Mercancía recibida de {cod}; revisar disponibilidad para venta",
            "entidad": "articulo", "entidad_ref": cod, "prioridad": "MEDIA", "datos": payload}


def _r_campana_finalizada(payload, id_empresa):
    camp = (payload or {}).get("campana") or (payload or {}).get("id")
    return {"dominio": "comercio", "tipo": "recomendacion", "titulo": "Retirar publicaciones de campaña",
            "descripcion": f"La campaña {camp} ha finalizado; conviene retirar sus publicaciones",
            "entidad": "campana", "entidad_ref": camp, "prioridad": "MEDIA", "datos": payload}


def _r_precio_cambiado(payload, id_empresa):
    cod = (payload or {}).get("codigo")
    return {"dominio": "comercio", "tipo": "recomendacion", "titulo": "Republicar en canales",
            "descripcion": f"Cambio de precio en {cod}; conviene republicar en los canales",
            "entidad": "articulo", "entidad_ref": cod, "prioridad": "MEDIA",
            "workflow": "comercio_republicar", "datos": payload}


def _r_proveedor_fallo(payload, id_empresa):
    prov = (payload or {}).get("proveedor")
    return {"dominio": "compras", "tipo": "riesgo", "titulo": "Recomendar proveedor alternativo",
            "descripcion": f"El proveedor {prov} ha fallado; evaluar alternativas",
            "entidad": "proveedor", "entidad_ref": prov, "prioridad": "ALTA", "datos": payload}


def _reglas_por_defecto():
    if _REGLAS:
        return
    registrar_regla("stock_bajo", _r_stock_bajo)
    registrar_regla("mercancia_recibida", _r_mercancia_recibida)
    registrar_regla("campana_finalizada", _r_campana_finalizada)
    registrar_regla("precio_cambiado", _r_precio_cambiado)
    registrar_regla("proveedor_fallo", _r_proveedor_fallo)


# ── Motor: disparador → propuesta (reutiliza el Centro de Decisiones) ─────────
def procesar(disparador, *, id_empresa=None, payload=None, actor="automatizacion"):
    """Ejecuta las reglas de un disparador. Cada regla PROPONE una decisión (nunca ejecuta). Devuelve
    los ids de decisión propuestos."""
    _reglas_por_defecto()
    from src.services import inteligencia
    propuestas = []
    for fn in _REGLAS.get(disparador, []):
        try:
            p = fn(payload or {}, id_empresa)
        except Exception as e:
            logger.debug("regla %s: %s", disparador, e)
            continue
        if not p:
            continue
        did = inteligencia.proponer(
            p.get("dominio", "general"), p.get("tipo", "recomendacion"), p.get("titulo"),
            p.get("descripcion"), entidad=p.get("entidad"), entidad_ref=p.get("entidad_ref"),
            prioridad=p.get("prioridad", "MEDIA"), workflow=p.get("workflow"), datos=p.get("datos"),
            origen=f"automatizacion:{disparador}", id_empresa=id_empresa, actor=actor)
        if did:
            propuestas.append(did)
    return {"ok": True, "disparador": disparador, "propuestas": propuestas}


# ── Integración con Event Bus real (mapa evento Enterprise → disparador lógico) ──
_MAPA_EVENTOS = {"STOCK_BAJO": "stock_bajo", "KARDEX_MOVIMIENTO": None,
                 "PublicationArchived": "campana_finalizada", "PublicationUpdated": None,
                 "CommerceConnectionRegistered": None}


def procesar_evento(tipo_evento, *, id_empresa=None, payload=None):
    """Traduce un evento del Event Bus a un disparador lógico y ejecuta sus reglas (si aplica)."""
    disp = _MAPA_EVENTOS.get(tipo_evento, None)
    if not disp:
        return {"ok": True, "ignorado": tipo_evento}
    return procesar(disp, id_empresa=id_empresa, payload=payload)


def suscribir():
    """Suscribe las automatizaciones a los eventos del Event Bus (capacidad, degradable/opt-in)."""
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is None or not hasattr(bus, "subscribe"):
            return False
        for evt in [e for e, d in _MAPA_EVENTOS.items() if d]:
            bus.subscribe(evt, lambda ev, _evt=evt: procesar_evento(
                _evt, id_empresa=(ev or {}).get("id_empresa"), payload=(ev or {}).get("payload")))
        return True
    except Exception as e:
        logger.debug("suscribir automatizaciones: %s", e)
        return False


def evaluar_periodico(id_empresa=None, *, actor="scheduler"):
    """Evaluación periódica (Scheduler): regenera decisiones (Centro de Decisiones) y propone circuitos
    Workflow para las decisiones de prioridad ALTA con `workflow_sugerido`. Solo PROPONE."""
    from src.services import inteligencia
    gen = inteligencia.generar(id_empresa, actor=actor)
    circuitos = 0
    for d in inteligencia.decisiones(id_empresa, prioridad="ALTA", usuario={"perfil": "SUPERADMIN"}):
        if d.get("workflow_sugerido"):
            circuitos += _proponer_circuito(d, id_empresa)
    return {"ok": True, "generadas": gen.get("generadas", 0), "circuitos_propuestos": circuitos}


def _proponer_circuito(decision, id_empresa):
    """Propone (no inicia sin aprobación) el circuito de Workflow sugerido por una decisión. Reutiliza
    Workflow por capacidad; degradable. Registra el vínculo, no ejecuta la acción de negocio."""
    try:
        from src.platform import capabilities as cap
        wf = cap.workflow()
        if wf is not None and hasattr(wf, "iniciar_proceso"):
            # Se PROPONE el proceso; su avance/ejecución sigue gobernado por Workflow + aprobación.
            wf.iniciar_proceso(decision.get("workflow_sugerido"),
                               entidad="decision_ia", entidad_id=decision.get("id"),
                               id_empresa=id_empresa)
            return 1
    except Exception as e:
        logger.debug("proponer circuito (%s): %s", decision.get("id"), e)
    return 0


def registrar_job():
    """Registra la evaluación periódica en el Scheduler (capacidad, degradable/opt-in)."""
    try:
        from src.platform import capabilities as cap
        sch = cap.scheduler()
        if sch is not None and hasattr(sch, "registrar_job"):
            sch.registrar_job("inteligencia_automatizacion", lambda *_a, **_k: evaluar_periodico())
            return True
    except Exception as e:
        logger.debug("registrar_job automatizacion: %s", e)
    return False


def descriptor() -> dict:
    _reglas_por_defecto()
    return {"servicio": "inteligencia.automatizacion", "etapa": "C", "fase": FASE,
            "estado": "implementado", "disparadores": disparadores(),
            "reutiliza": ["eventbus", "scheduler", "workflow", "rules", "inteligencia"],
            "solo_propone": True, "modifica_datos": False, "motor_nuevo": False}


__all__ = ["FASE", "registrar_regla", "disparadores", "procesar", "procesar_evento", "suscribir",
           "evaluar_periodico", "registrar_job", "descriptor"]
