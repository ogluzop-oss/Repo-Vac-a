"""
Motor LLM real de SOMA (Anthropic + tool-use), reutilizando el registro de tools MCP ya construido
(`src.mcp_server.registry`). PUNTO DE ENTRADA: `responder_con_llm(texto, usuario, id_empresa)`.

Arquitectura (ver el plan de migracion para el detalle completo): sustituye el "cerebro" de
`src.soma.kernel._consultar_cerebro` como ruta PRINCIPAL para preguntas/instrucciones complejas,
con `CopilotService.preguntar()` (motor determinista) como FALLBACK automatico — nunca un error
crudo al usuario. Reutiliza TAL CUAL: `ejecutar_tarea_ia`/`resolver_tenant_actual`
(`ia_control_uso.py`, mismo control de coste que `ai_translator.py`/`mapeo_ia.py`/
`factura_ocr_ia.py`) y `mcp_server.registry.{listar_tools,obtener_tool,ejecutar_tool,
fijar_contexto_actual,limpiar_contexto_actual}` (el mismo registro que usa el servidor MCP
externo — un segundo consumidor interno, no una reescritura).

GOBERNANZA (defensa en profundidad, ver `registry.py::registrar_tool`): las tools de ESCRITURA
(`requiere_confirmacion=True`) NUNCA se ejecutan en el momento en que Claude decide llamarlas —
se guardan como PENDIENTES (`historial_llm.anadir_turno(..., tool_result=None)`) y SOMA pregunta
al usuario; solo una confirmacion explicita en el turno SIGUIENTE ejecuta la tool de verdad.
Las tools de SOLO LECTURA se ejecutan de inmediato (no tiene sentido interrumpir para preguntar
permiso antes de consultar un dato).

Degradacion honesta (nunca un error crudo): sin `ANTHROPIC_API_KEY`/paquete `anthropic` → fallback
SILENCIOSO (mismo criterio que los 3 integradores existentes, condicion de DESPLIEGUE, no un fallo
en tiempo de ejecucion); `LimiteUsoIAExcedido`/`RateLimitError`/`APITimeoutError`/`APIStatusError`/
CUALQUIER OTRO error inesperado → fallback con mensaje amable (NINGUN fallo real en tiempo de
ejecucion queda silencioso: solo la ausencia de API key, que no es un fallo). En todos los casos de
fallback, `responder_con_llm` devuelve `{"via": "fallback_needed", ...}` (nunca lanza) para que
`kernel.py` decida caer al motor determinista sin ruido.
"""

from __future__ import annotations

import json
import logging
import os

from src.mcp_server.registry import (ejecutar_tool, fijar_contexto_actual,
                                      limpiar_contexto_actual, listar_tools, obtener_tool)
from src.services.copilot import historial_llm
from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia, resolver_tenant_actual

logger = logging.getLogger("copilot.motor_llm")

try:
    import anthropic
except Exception:  # pragma: no cover - degradacion si el paquete no esta instalado
    anthropic = None

_MODELO = os.getenv("SMART_MANAGER_SOMA_MODEL", "claude-haiku-4-5-20251001")
_MAX_TOKENS = 1500
_MAX_ITERACIONES_TOOL_USE = 5

SYSTEM_PROMPT = (
    "Eres SOMA, el copiloto de inteligencia artificial residente de Smart Manager AI (ERP de "
    "gestion de almacen/tienda). Tu personalidad es profesional, cercana y CONCISA — respondes "
    "en espanol, con formato Markdown (listas, negritas, tablas sencillas cuando ayuden a leer "
    "cifras), sin rodeos innecesarios.\n\n"
    "REGLAS DE HONESTIDAD (criticas, nunca las rompas):\n"
    "1. NUNCA inventes una cifra, stock, venta, movimiento o dato de negocio. Si la pregunta "
    "necesita un dato real, USA SIEMPRE la tool correspondiente antes de responder; si ninguna "
    "tool cubre lo que te piden, dilo honestamente en vez de aproximar un numero.\n"
    "2. Crear un borrador de pedido de compra o modificar el catalogo (altas/ediciones de "
    "producto o categoria) son acciones SENSIBLES. El mecanismo de confirmacion lo gestiona el "
    "propio sistema, NO tu: en cuanto decidas que la peticion del usuario requiere una de esas "
    "tools, LLAMA A LA TOOL DE INMEDIATO con los mejores argumentos que puedas inferir (el "
    "sistema NUNCA la ejecuta en el acto — intercepta la llamada, la deja pendiente y se la "
    "resume al usuario pidiendo su confirmacion automaticamente). NUNCA te limites a describir "
    "en texto plano lo que harias ni pidas confirmacion tu mismo en prosa SIN llamar a la tool —"
    " si no llamas a la tool, el sistema no tiene nada que confirmar y la peticion del usuario "
    "se queda sin efecto. Resume con claridad (articulo, cantidad, proveedor, campos a "
    "cambiar...) en tu texto de acompañamiento de esa misma llamada, para que el usuario sepa "
    "exactamente que va a confirmar.\n"
    "3. NUNCA afirmes que una accion 'ya se ha hecho' o 'ya esta creada' hasta que el usuario "
    "haya confirmado explicitamente y el sistema te confirme el resultado real. Proponer no es "
    "ejecutar.\n"
    "4. Si una pregunta es ambigua o le falta un dato imprescindible (p. ej. que articulo, que "
    "rango de fechas), pregunta antes de adivinar."
)

_AFIRMATIVOS = {
    "si", "sí", "vale", "confirmo", "adelante", "ok", "okay", "dale", "va", "hazlo",
    "correcto", "exacto", "afirmativo", "claro", "perfecto", "procede", "confirmado",
}


# ============================================================
# GUARDA DE DISPONIBILIDAD (mismo patron que `ai_translator._anthropic_backend`)
# ============================================================
def _cliente():
    """Cliente Anthropic si hay paquete `anthropic` y `ANTHROPIC_API_KEY`; None si no (degradacion
    silenciosa, identica a los 3 integradores ya existentes)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or anthropic is None:
        return None
    try:
        return anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        logger.debug("motor_llm: no se pudo crear el cliente Anthropic: %s", e)
        return None


def _es_afirmativo(texto) -> bool:
    """Clasificador determinista (NO una llamada a LLM): primera palabra de `texto`, normalizada,
    frente a una lista de afirmativos habituales en espanol. Cualquier otra cosa (incluida
    ambiguedad) se trata como negativo — nunca se ejecuta por omision ni por duda."""
    t = (texto or "").strip().lower().strip(" .!¡?¿")
    if not t:
        return False
    primera = t.split()[0] if t.split() else t
    return primera in _AFIRMATIVOS


def _construir_ctx(id_empresa):
    """Contexto para `registry.ejecutar_tool` — identidad real de la sesion de escritorio activa
    (NUNCA de un argumento de usuario), mismo criterio multi-tenant que el resto del sistema."""
    usuario_dict = {}
    try:
        from src.db.usuario import sesion_global
        usuario_dict = dict(sesion_global.usuario_actual or {})
    except Exception:
        pass
    return {"usuario": usuario_dict, "id_empresa": id_empresa, "auth": "desktop"}


def _tools_anthropic() -> list[dict]:
    """`listar_tools()` (MCP) → formato `tools=[...]` de Anthropic (1:1, mismo JSON Schema)."""
    return [{"name": t["nombre"], "description": t["descripcion"], "input_schema": t["schema"]}
            for t in listar_tools()]


def _ejecutar_tool_segura(ctx, nombre_tool, argumentos) -> dict:
    """Ejecuta una tool MCP fijando/limpiando el contexto SIEMPRE (incluso si falla) — nunca deja
    un contexto de empresa ajeno pegado al hilo tras un error."""
    try:
        fijar_contexto_actual(ctx)
        return ejecutar_tool(nombre_tool, argumentos)
    except Exception as e:
        logger.info("motor_llm: tool '%s' fallo: %s", nombre_tool, e)
        return {"error": str(e)}
    finally:
        limpiar_contexto_actual()


def _llamar_claude(cliente, mensajes, tools_api, id_empresa, id_usuario):
    def _llamar():
        return cliente.messages.create(
            model=_MODELO, max_tokens=_MAX_TOKENS, system=SYSTEM_PROMPT,
            messages=mensajes, tools=tools_api,
        )
    return ejecutar_tarea_ia(id_empresa, id_usuario, "soma_chat", _llamar)


def _texto_de(respuesta) -> str:
    return "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()


def _con_tool_result(mensajes, respuesta, bloque_tool_use, resultado_tool) -> list[dict]:
    """Añade al historial EN MEMORIA (solo para esta llamada, no se persiste así en BD) el turno
    assistant con el `tool_use` real + el `tool_result` correspondiente, para que Claude pueda
    razonar sobre el dato real en la siguiente vuelta del bucle."""
    return mensajes + [
        {"role": "assistant", "content": respuesta.content},
        {"role": "user", "content": [{
            "type": "tool_result",
            "tool_use_id": bloque_tool_use.id,
            "content": json.dumps(resultado_tool, ensure_ascii=False, default=str),
        }]},
    ]


# ============================================================
# CONFIRMACION PENDIENTE (turno siguiente a una propuesta de tool de ESCRITURA)
# ============================================================
def _resolver_confirmacion(pendiente, texto, usuario, id_empresa, ctx, cliente, id_usuario):
    """Interpreta `texto` como respuesta a una propuesta pendiente. Afirmativo → ejecuta la tool
    DE VERDAD ahora y devuelve la respuesta final (dict). Cualquier otra cosa → cancela la
    propuesta y devuelve None (el llamador trata `texto` como un turno nuevo, normal)."""
    if not _es_afirmativo(texto):
        historial_llm.resolver_turno_pendiente(pendiente["id"], {"cancelado": True})
        return None

    nombre_tool = pendiente["tool_name"]
    argumentos = pendiente["tool_args"] or {}
    resultado_tool = _ejecutar_tool_segura(ctx, nombre_tool, argumentos)
    historial_llm.resolver_turno_pendiente(pendiente["id"], resultado_tool)
    historial_llm.anadir_turno(usuario, id_empresa, "user", texto)

    # Pide a Claude un cierre natural a partir del resultado REAL (sin tools: ya se ejecuto,
    # este paso solo redacta la confirmacion/explicacion del error al usuario).
    historial = historial_llm.obtener_historial(usuario, id_empresa, limite=20)
    if historial and historial[-1]["role"] == "user":
        historial = historial[:-1]   # se sustituye por el mensaje combinado de abajo
    mensaje_cierre = {
        "role": "user",
        "content": (
            f"{texto}\n\n[Resultado real tras confirmar la herramienta '{nombre_tool}': "
            f"{json.dumps(resultado_tool, ensure_ascii=False, default=str)}. Redacta ahora una "
            "respuesta breve y natural en espanol confirmando al usuario lo sucedido, o "
            "explicando el error con amabilidad si lo hay. No inventes datos que no esten en "
            "el resultado.]"
        ),
    }
    try:
        respuesta = _llamar_claude(cliente, historial + [mensaje_cierre], [], id_empresa, id_usuario)
        texto_final = _texto_de(respuesta) or "Listo, ya está."
    except (LimiteUsoIAExcedido, getattr(anthropic, "RateLimitError", Exception),
            getattr(anthropic, "APITimeoutError", Exception),
            getattr(anthropic, "APIStatusError", Exception)):
        # La accion YA se ejecuto (o fallo) de verdad; aunque el cierre narrativo falle, el
        # resultado real no se oculta — se informa con un mensaje honesto y simple.
        if resultado_tool.get("error"):
            texto_final = f"Se ha intentado la accion pero ha fallado: {resultado_tool['error']}"
        else:
            texto_final = "Hecho — la accion se ha ejecutado correctamente."
    historial_llm.anadir_turno(usuario, id_empresa, "assistant", texto_final)
    return {"texto": texto_final, "via": "llm"}


# ============================================================
# TURNO NORMAL (sin confirmacion pendiente): bucle de tool-use
# ============================================================
def _turno_normal(texto, usuario, id_empresa, ctx, cliente, id_usuario) -> dict:
    historial_llm.anadir_turno(usuario, id_empresa, "user", texto)
    mensajes = historial_llm.obtener_historial(usuario, id_empresa, limite=20)
    tools_api = _tools_anthropic()

    for _ in range(_MAX_ITERACIONES_TOOL_USE):
        respuesta = _llamar_claude(cliente, mensajes, tools_api, id_empresa, id_usuario)
        bloques_tool_use = [b for b in respuesta.content if getattr(b, "type", "") == "tool_use"]
        texto_resp = _texto_de(respuesta)

        if not bloques_tool_use:
            texto_final = texto_resp or "No he podido generar una respuesta; ¿puedes reformular la pregunta?"
            historial_llm.anadir_turno(usuario, id_empresa, "assistant", texto_final)
            return {"texto": texto_final, "via": "llm"}

        bloque = bloques_tool_use[0]   # alcance actual: una tool por vuelta (sin paralelismo)
        nombre_tool = bloque.name
        argumentos = bloque.input or {}
        tool_meta = obtener_tool(nombre_tool)

        if tool_meta is not None and tool_meta.get("requiere_confirmacion"):
            resumen = texto_resp or (
                f"Voy a usar la herramienta «{nombre_tool}» con estos datos: "
                f"{json.dumps(argumentos, ensure_ascii=False, default=str)}. ¿Confirmas?"
            )
            historial_llm.anadir_turno(usuario, id_empresa, "tool", resumen,
                                       tool_name=nombre_tool, tool_args=argumentos, tool_result=None)
            historial_llm.anadir_turno(usuario, id_empresa, "assistant", resumen)
            return {"texto": resumen, "via": "llm", "pendiente_confirmacion": True}

        if tool_meta is None:
            resultado_tool = {"error": f"Tool desconocida: {nombre_tool}"}
        else:
            resultado_tool = _ejecutar_tool_segura(ctx, nombre_tool, argumentos)
        mensajes = _con_tool_result(mensajes, respuesta, bloque, resultado_tool)

    texto_final = ("He necesitado demasiados pasos para resolver esto; prueba a reformular la "
                  "pregunta de forma más concreta.")
    historial_llm.anadir_turno(usuario, id_empresa, "assistant", texto_final)
    return {"texto": texto_final, "via": "llm"}


# ============================================================
# PUNTO DE ENTRADA
# ============================================================
def responder_con_llm(texto, usuario, id_empresa) -> dict:
    """Responde `texto` vía Anthropic con tool-use real. Devuelve SIEMPRE un dict, nunca lanza:
    éxito → `{"texto": str, "via": "llm", ...}`; degradación → `{"via": "fallback_needed",
    "motivo": str, "texto"?: str}` para que `kernel.py` caiga al motor determinista existente."""
    cliente = _cliente()
    if cliente is None:
        return {"via": "fallback_needed", "motivo": "sin_api_key"}

    id_empresa_sesion, id_usuario_sesion = resolver_tenant_actual()
    id_empresa_efectivo = id_empresa_sesion or id_empresa
    if not id_empresa_efectivo or not usuario:
        return {"via": "fallback_needed", "motivo": "sin_contexto"}

    ctx = _construir_ctx(id_empresa_efectivo)

    try:
        pendiente = historial_llm.obtener_turno_pendiente(usuario, id_empresa_efectivo)
        if pendiente is not None:
            resultado = _resolver_confirmacion(pendiente, texto, usuario, id_empresa_efectivo,
                                               ctx, cliente, id_usuario_sesion)
            if resultado is not None:
                return resultado
            # Negativo/cancelado: cae al turno normal de abajo (mensaje nuevo, nada ejecutado).

        return _turno_normal(texto, usuario, id_empresa_efectivo, ctx, cliente, id_usuario_sesion)

    except LimiteUsoIAExcedido:
        return {
            "via": "fallback_needed", "motivo": "limite_ia",
            "texto": "He alcanzado el límite de uso de IA de hoy para tu empresa; te respondo "
                     "con el motor habitual mientras tanto.",
        }
    except Exception as e:
        if anthropic is not None and isinstance(e, (anthropic.RateLimitError, anthropic.APITimeoutError,
                                                      anthropic.APIStatusError)):
            logger.warning("motor_llm: error de Anthropic (%s), fallback al motor determinista: %s",
                           type(e).__name__, e)
            return {
                "via": "fallback_needed", "motivo": "error_anthropic",
                "texto": "Ahora mismo tengo problemas para conectar con mi motor avanzado; te "
                         "respondo con el motor habitual.",
            }
        logger.error("motor_llm: error inesperado, fallback al motor determinista: %s", e)
        return {
            "via": "fallback_needed", "motivo": "error_inesperado",
            "texto": "He tenido un problema inesperado al usar mi motor avanzado; te respondo "
                     "con el motor habitual mientras tanto.",
        }


__all__ = ["responder_con_llm", "SYSTEM_PROMPT"]
