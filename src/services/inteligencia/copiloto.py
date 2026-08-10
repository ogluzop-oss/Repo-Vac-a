"""
Etapa C · Fase C4 — Copiloto Empresarial (Área 8).

Capa de CONSULTA transversal: responde preguntas de negocio ("¿qué está ocurriendo?", "¿qué debería
hacer?", "¿qué riesgos hay?") REUTILIZANDO el Centro de Decisiones (C1), el Panel (C3) y el motor de
consultas NL existente (`ia.consultas`). SIEMPRE con datos verificables; NUNCA inventa (si no hay
datos, lo dice). RBAC (`inteligencia.ver`); la respuesta se filtra por lo que el usuario puede ver.
No crea una IA nueva ni modifica datos. Auditable (evento de consulta). Multiempresa. Degradable.
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger("inteligencia.copiloto")

FASE = "C4"


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return t


def _tiene(t, *claves):
    return any(c in t for c in claves)


def _intent(texto):
    t = _norm(texto)
    if _tiene(t, "riesgo", "peligro"):
        return "riesgos"
    if _tiene(t, "alerta"):
        return "alertas"
    if _tiene(t, "deberia hacer", "que hago", "que hacer", "priorizar", "prioridad", "atencion",
              "urgente"):
        return "acciones"
    if _tiene(t, "que ocurre", "esta ocurriendo", "esta pasando", "situacion", "resumen", "estado",
              "como vamos"):
        return "situacion"
    return "libre"


def _emp(id_empresa=None):
    from src.services import inteligencia
    return inteligencia._emp(id_empresa)


def _perfil(usuario):
    return (usuario or {}).get("perfil") if isinstance(usuario, dict) else None


def _evento(emp, intent, usuario):
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is not None and hasattr(bus, "publish"):
            bus.publish("CopilotQuery", id_empresa=emp, origen="inteligencia.copiloto",
                        ref_entidad="copiloto", payload={"intent": intent,
                        "usuario": (usuario or {}).get("id") if isinstance(usuario, dict) else None})
    except Exception:
        pass


def _resp(intent, texto, datos=None, fuente=None, recomendaciones=None):
    return {"intent": intent, "texto": texto, "datos": datos or [], "fuente": fuente,
            "recomendaciones": recomendaciones or [], "verificable": bool(datos)}


def preguntar(texto, *, id_empresa=None, usuario=None):
    """Responde una pregunta de negocio reutilizando la capa de inteligencia. RBAC: `inteligencia.ver`.
    Nunca inventa: si no hay datos verificables, lo indica explícitamente."""
    from src.services import inteligencia
    from src.services.inteligencia import panel
    emp = _emp(id_empresa)
    if not inteligencia._puede(usuario, "inteligencia.ver", emp):
        return _resp("no_autorizado", "No tienes permiso para consultar la inteligencia empresarial.")
    intent = _intent(texto)
    _evento(emp, intent, usuario)

    if intent == "situacion":
        p = panel.panel(emp, usuario=usuario)
        r = p.get("resumen_decisiones", {})
        als = p.get("alertas", [])[:5]
        txt = (f"Situación: {r.get('total', 0)} decisiones abiertas "
               f"({r.get('por_prioridad', {}).get('ALTA', 0)} de prioridad ALTA), "
               f"{p.get('totales', {}).get('alertas', 0)} alertas.")
        return _resp("situacion", txt, {"resumen": r, "alertas": als,
                     "totales": p.get("totales")}, fuente="panel+centro")

    if intent == "acciones":
        prio = inteligencia.decisiones(emp, prioridad="ALTA", usuario=usuario, limite=10)
        if not prio:
            return _resp("acciones", "No hay acciones prioritarias pendientes ahora mismo.",
                         fuente="centro")
        return _resp("acciones", f"{len(prio)} acciones prioritarias: " +
                     "; ".join(d.get("titulo", "") for d in prio[:5]),
                     [d for d in prio], fuente="centro")

    if intent == "riesgos":
        rs = (inteligencia.decisiones(emp, tipo="riesgo", usuario=usuario, limite=20) +
              inteligencia.decisiones(emp, tipo="anomalia", usuario=usuario, limite=20))
        if not rs:
            return _resp("riesgos", "No se detectan riesgos ni anomalías abiertos.", fuente="centro")
        return _resp("riesgos", f"{len(rs)} riesgos/anomalías: " +
                     "; ".join(d.get("titulo", "") for d in rs[:5]), rs, fuente="centro")

    if intent == "alertas":
        als = panel.alertas(emp, usuario=usuario, limite=20)
        return _resp("alertas", f"{len(als)} alertas activas." if als else "Sin alertas activas.",
                     als, fuente="panel")

    # Libre → motor de consultas NL existente (data-backed). Nunca inventa.
    try:
        from src.services.ia import consultas
        r = consultas.responder(texto, id_empresa=emp, usuario=usuario, perfil=_perfil(usuario))
        d = r.to_dict() if hasattr(r, "to_dict") else (r if isinstance(r, dict) else {})
        if d.get("intent") in (None, "desconocido", "vacio", "desactivado"):
            return _resp("no_verificable",
                         "No dispongo de datos verificables para responder eso con precisión.")
        return _resp(d.get("intent"), d.get("texto"), d.get("datos"), fuente="ia.consultas",
                     recomendaciones=d.get("recomendaciones"))
    except Exception as e:
        logger.debug("consulta libre: %s", e)
        return _resp("no_verificable",
                     "No dispongo de datos verificables para responder eso con precisión.")


def descriptor() -> dict:
    return {"servicio": "inteligencia.copiloto", "etapa": "C", "fase": FASE, "estado": "implementado",
            "reutiliza": ["inteligencia (Centro)", "inteligencia.panel", "ia.consultas"],
            "intents": ["situacion", "acciones", "riesgos", "alertas", "libre"],
            "solo_lectura": True, "modifica_datos": False, "inventa": False, "motor_nuevo": False}


__all__ = ["FASE", "preguntar", "descriptor"]
