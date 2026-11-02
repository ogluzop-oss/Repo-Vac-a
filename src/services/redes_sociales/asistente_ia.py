"""
Sugerencia de respuesta con IA para la bandeja de entrada, conectada a la base de conocimiento
interna real (`services.sat.kb.buscar` — la misma KB de Posventa/SAT, reutilizada tal cual, sin
crear una segunda base de artículos). Envoltorio NUEVO y DELIBERADAMENTE LIGERO: ni
`services.copilot.motor_llm` (pensado para turnos de chat con tool-use/historial persistente, que
aquí no aplica — sugerir una respuesta a un DM es una tarea de un solo disparo) ni
`services.ccp.ia_asistente` (plantillas deterministas sin ningún grounding real) encajaban. Este
módulo reutiliza TAL CUAL el resto de la infraestructura de IA ya construida: construcción del
cliente Anthropic (mismo patrón que `motor_llm._cliente`) y el control de coste/uso por empresa
(`services.ia_control_uso.ejecutar_tarea_ia`/`resolver_tenant_actual`/`LimiteUsoIAExcedido`).

Degradación honesta: sin `ANTHROPIC_API_KEY`/paquete `anthropic` → `{"via": "fallback_needed", ...}`
(nunca un texto inventado hecho pasar por IA).
"""

import logging
import os

from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia, resolver_tenant_actual

logger = logging.getLogger("redes_sociales.asistente_ia")

try:
    import anthropic
except Exception:
    anthropic = None

_MODELO = os.getenv("SMART_MANAGER_SOMA_MODEL", "claude-haiku-4-5-20251001")
_MAX_TOKENS = 500

SYSTEM_PROMPT = (
    "Eres el asistente de atención al cliente en redes sociales de una empresa que usa Smart "
    "Manager AI. Redactas UNA sugerencia de respuesta breve, profesional y cercana al mensaje "
    "entrante, en el MISMO idioma del mensaje. Si se te da contexto de la base de conocimiento "
    "interna, básate en él para la información concreta (políticas, plazos, procedimientos) y "
    "NUNCA inventes un dato (precio, plazo, política) que no esté en ese contexto o en el propio "
    "mensaje. Si no tienes suficiente información para una parte de la respuesta, sé honesto y "
    "genérico en esa parte en vez de inventar. Devuelve SOLO el texto de la respuesta sugerida, "
    "sin comillas ni explicaciones adicionales."
)


def disponible() -> bool:
    return anthropic is not None and bool(os.getenv("ANTHROPIC_API_KEY"))


def _cliente():
    if not disponible():
        return None
    try:
        return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception as e:
        logger.debug("asistente_ia: no se pudo crear el cliente Anthropic: %s", e)
        return None


def sugerir_respuesta(texto_mensaje, *, cliente_nombre=None, id_empresa=None) -> dict:
    """Devuelve `{"via": "ia", "texto": "..."}` o `{"via": "fallback_needed", "motivo": "..."}`.
    Busca contexto relevante en la KB de SAT (`kb.buscar`) por las primeras palabras del mensaje;
    best-effort, nunca bloquea la sugerencia si la KB no devuelve nada."""
    texto_mensaje = (texto_mensaje or "").strip()
    if not texto_mensaje:
        return {"via": "fallback_needed", "motivo": "mensaje_vacio"}

    cli = _cliente()
    if cli is None:
        return {"via": "fallback_needed", "motivo": "ia_no_configurada"}

    contexto_kb = ""
    try:
        from src.services.sat.kb import buscar, ver_articulo
        resumen = buscar(texto_mensaje, id_empresa=id_empresa, limite=3) or []
        completos = [ver_articulo(a["id"]) for a in resumen if a.get("id")]
        if completos:
            contexto_kb = "\n\n".join(
                f"[{a.get('titulo')}] {(a.get('cuerpo') or '')[:400]}" for a in completos if a)
    except Exception as e:
        logger.debug("sugerir_respuesta: kb.buscar: %s", e)

    id_empresa_sesion, id_usuario_sesion = resolver_tenant_actual()
    id_empresa = id_empresa or id_empresa_sesion

    prompt = f"Mensaje del cliente"
    if cliente_nombre:
        prompt += f" ({cliente_nombre})"
    prompt += f":\n{texto_mensaje}"
    if contexto_kb:
        prompt += f"\n\nContexto de la base de conocimiento interna:\n{contexto_kb}"

    def _llamar():
        return cli.messages.create(model=_MODELO, max_tokens=_MAX_TOKENS, system=SYSTEM_PROMPT,
                                   messages=[{"role": "user", "content": prompt}])

    try:
        respuesta = ejecutar_tarea_ia(id_empresa, id_usuario_sesion, "redes_sociales_sugerencia",
                                      _llamar)
    except LimiteUsoIAExcedido:
        return {"via": "fallback_needed", "motivo": "limite_uso_ia_excedido"}
    except Exception as e:
        if anthropic is not None and isinstance(
                e, (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIStatusError)):
            logger.info("sugerir_respuesta: error Anthropic: %s", e)
            return {"via": "fallback_needed", "motivo": "error_ia"}
        logger.error("sugerir_respuesta: %s", e)
        return {"via": "fallback_needed", "motivo": "error_interno"}

    bloques = [b.text for b in getattr(respuesta, "content", []) if getattr(b, "type", "") == "text"]
    texto = "\n".join(bloques).strip()
    if not texto:
        return {"via": "fallback_needed", "motivo": "respuesta_vacia"}
    return {"via": "ia", "texto": texto, "con_contexto_kb": bool(contexto_kb)}
