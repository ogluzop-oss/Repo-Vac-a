"""
Registro de tools MCP — PUNTO DE EXTENSIÓN para agentes futuros.

Este módulo NO implementa lógica de negocio: es solo el mecanismo por el que una tool se da de
alta. Para añadir una tool real (stock/ventas/catálogo/pedidos/...), un agente futuro escribe un
módulo nuevo (p. ej. `src/mcp_server/tools/stock.py`) que llama a `registrar_tool(...)` una vez,
al importarse, y lo importa desde `_cargar_tools_incorporadas()` más abajo. El handler recibe
`(ctx, argumentos)`:

  - `ctx`: el mismo contexto autenticado que ya usa el resto de la REST API
    (`src.api.security.contexto_de_request()` → `{"usuario": {...}, "id_empresa": ..., "auth": ...}`).
    El `id_empresa`/`usuario` SIEMPRE sale del JWT validado en `transport.py`, nunca de los
    argumentos de la tool — mismo invariante multi-tenant que el resto del sistema.
  - `argumentos`: el dict `arguments` tal cual lo manda el cliente MCP (ya validado contra el
    JSON Schema de la tool por el propio SDK `mcp` antes de llegar aquí).

Debe devolver un dict JSON-serializable (se envuelve en un `TextContent` de texto JSON por
`transport.py`); para señalar un error de negocio, levantar una excepción normal — `transport.py`
la convierte en `CallToolResult(isError=True, ...)` sin romper el canal JSON-RPC.

Gobernanza (recordatorio para quien añada tools de ESCRITURA, ver CLAUDE.md): SOMA es un
orquestador basado en reglas que NUNCA ejecuta acciones directamente — cualquier tool que
modifique datos debe enrutar la operación como una PROPUESTA a través de
`src.services.copilot.acciones.solicitar()` (Workflow/Gobierno, aprobación humana), exactamente
igual que el resto de SOMA. Una tool de solo lectura no tiene esa restricción.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger("mcp_server.registry")

_TOOLS: dict[str, dict] = {}

# Contexto autenticado de la llamada en curso, indexado por hilo del servidor WSGI (cada
# request Flask se sirve en su propio hilo; ver nota de concurrencia en `transport.py`).
_CONTEXTO_POR_HILO: dict[int, dict] = {}


def registrar_tool(nombre: str, descripcion: str, schema: dict, handler: Callable[[dict, dict], dict],
                    requiere_confirmacion: bool = False) -> None:
    """Da de alta una tool MCP. `schema` es un JSON Schema de `arguments` (draft 2020-12, como
    exige el SDK `mcp`). Llamar una sola vez por nombre (una re-registración sustituye la
    anterior — útil en recarga en caliente durante desarrollo, nunca en producción).

    `requiere_confirmacion` (por defecto False): SOLO lo consume el pipeline interno de SOMA
    (`services/copilot/motor_llm.py`) — NO afecta en absoluto al servidor MCP externo
    (`transport.py`), que sigue llamando `ejecutar_tool` exactamente igual que siempre, con su
    propia garantía (toda tool de escritura ya crea un borrador/propuesta, nunca ejecuta de
    verdad). Marca una SEGUNDA capa de seguridad, propia del pipeline LLM en proceso: cuando es
    True, `motor_llm.py` NO ejecuta la tool al momento de decidirla — la deja pendiente de que el
    usuario la confirme explícitamente en su turno siguiente (ver `historial_llm.py`)."""
    if nombre in _TOOLS:
        logger.warning("Tool MCP '%s' re-registrada (sustituye la anterior)", nombre)
    _TOOLS[nombre] = {"nombre": nombre, "descripcion": descripcion, "schema": schema, "handler": handler,
                       "requiere_confirmacion": bool(requiere_confirmacion)}


def listar_tools() -> list[dict]:
    return list(_TOOLS.values())


def obtener_tool(nombre: str) -> dict | None:
    return _TOOLS.get(nombre)


def ejecutar_tool(nombre: str, argumentos: dict) -> dict:
    tool = obtener_tool(nombre)
    if not tool:
        raise ValueError(f"Tool desconocida: {nombre}")
    ctx = obtener_contexto_actual()
    if ctx is None:
        raise PermissionError("Sin contexto autenticado")
    return tool["handler"](ctx, argumentos or {})


def fijar_contexto_actual(ctx: dict) -> None:
    _CONTEXTO_POR_HILO[threading.get_ident()] = ctx


def obtener_contexto_actual() -> dict | None:
    return _CONTEXTO_POR_HILO.get(threading.get_ident())


def limpiar_contexto_actual() -> None:
    _CONTEXTO_POR_HILO.pop(threading.get_ident(), None)


# ── Tool trivial de prueba (task 3 del encargo): demuestra la cadena completa de extremo a
#    extremo (DCR → authorize → token → /mcp → tools/call) sin tocar ninguna lógica de negocio. ──
def _tool_whoami(ctx: dict, argumentos: dict) -> dict:
    usuario = ctx.get("usuario") or {}
    return {
        "usuario": usuario.get("nombre"),
        "id_usuario": usuario.get("id"),
        "perfil": usuario.get("perfil"),
        "id_empresa": ctx.get("id_empresa"),
        "auth": ctx.get("auth"),
    }


def _cargar_tools_incorporadas() -> None:
    registrar_tool(
        "whoami",
        "Devuelve la identidad (usuario/empresa/rol) resuelta a partir del token Bearer "
        "con el que se llamó a este servidor MCP. Tool de diagnóstico/ejemplo — no hace nada más.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        _tool_whoami,
    )

    from src.mcp_server.tools_lectura import registrar_herramientas_lectura
    registrar_herramientas_lectura()

    from src.mcp_server.tools_escritura import registrar_herramientas_escritura
    registrar_herramientas_escritura()


_cargar_tools_incorporadas()

__all__ = ["registrar_tool", "listar_tools", "obtener_tool", "ejecutar_tool",
           "fijar_contexto_actual", "obtener_contexto_actual", "limpiar_contexto_actual"]
