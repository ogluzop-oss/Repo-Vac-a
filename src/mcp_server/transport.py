"""
Transporte MCP (Model Context Protocol) — Streamable HTTP sobre el backend Flask/WSGI existente.

DECISIÓN DE INGENIERÍA (task 1 del encargo) Y RAZONAMIENTO
============================================================
El SDK oficial `mcp` (`pip install mcp`) construye su transporte "Streamable HTTP" de referencia
(`Server.streamable_http_app()`, `StreamableHTTPSessionManager`) exclusivamente sobre Starlette/
ASGI: monta rutas Starlette, exige su propio `lifespan`, y su gestor de sesión asume un servidor
ASGI (uvicorn/hypercorn) sirviendo la conexión. Smart Manager es Flask/WSGI (`src/backend/app.py`)
y el requisito explícito era `/mcp` en el MISMO puerto (8090) que el resto del backend, sin
reverse proxy ni subproceso. Se evaluaron tres caminos:

  (a) Montar el `Starlette` que devuelve `Server.streamable_http_app()` vía un puente WSGI↔ASGI
      (p. ej. `asgiref.wsgi.WsgiToAsgi` inverso, o correr un servidor ASGI en un hilo aparte
      detrás de un proxy interno). Descartado: añade un runtime HTTP entero (uvicorn) y una
      capa de puente solo para una ruta, contradice "mismo proceso, mismo puerto, sin proxy",
      y duplica trabajo que Flask ya hace (parseo de la petición, cabeceras, etc).

  (b) Reimplementar el protocolo Streamable HTTP ENTERO a mano, incluida la sesión persistente
      multi-petición con `anyio` memory streams que espera `Server.run()` (que modela una
      conexión bidireccional de larga duración, no peticiones HTTP independientes). Descartado
      por desproporcionado: el propio SDK expone un soporte OFICIAL para el caso "sin sesión
      persistente" (`stateless_http=True` en `streamable_http_app()`), que es exactamente la
      semántica que necesitamos (cada tool-call de SOMA es una operación autocontenida, sin
      estado de conversación en el servidor) — reimplementar esa parte sería inventar un motor
      paralelo de algo que el SDK ya reconoce como un modo válido.

  (c) ELEGIDA: usar `mcp.server.lowlevel.Server` como lo que realmente es por diseño — una clase
      agnóstica de transporte. `Server.request_handlers` es un dict PÚBLICO `{tipo_de_Request:
      handler_async}` que los decoradores `@server.list_tools()`/`@server.call_tool()` rellenan;
      nada obliga a invocarlo a través de `Server.run()`/`anyio`. Cada POST a `/mcp` construye el
      objeto `types.XRequest` correspondiente al método JSON-RPC recibido y hace
      `asyncio.run(server.request_handlers[tipo](req))` directamente — UNA petición HTTP, UNA
      ejecución de evento-loop autocontenida, CERO estado compartido entre peticiones salvo lo
      que ya vive en la BD (igual que cualquier otra vista Flask de este backend). Verificado a
      mano (ver commit/sesión de verificación): da como resultado un `ListToolsResult`/
      `CallToolResult` con el mismo volcado JSON que produciría el SDK por su camino oficial.

      Ventaja clave sobre (a)/(b): seguimos beneficiándonos del SDK para lo que de verdad aporta
      — los modelos Pydantic de `mcp.types` (validación/serialización fiel a la especificación,
      negociación de versión, capacidades) y el registro de tools vía decoradores — sin arrastrar
      Starlette/uvicorn ni reinventar la máquina de estados de sesión. El precio es explícito y
      documentado aquí: NO hay GET /mcp con streaming SSE servidor→cliente (el modo degenerado
      "petición POST → una respuesta JSON" cubre tools/list y tools/call, que es todo lo que este
      scaffold necesita; sampling/progreso incremental quedan fuera de alcance de esta pieza
      fundacional) y no hay sesión persistente entre peticiones (aceptable: nuestras tools son
      stateless — el `Mcp-Session-Id` se emite y se ecoa por compatibilidad de protocolo, pero no
      referencia ningún estado en memoria).

Identificación del servidor (task 4): `serverInfo.name` = "SOMA — Smart Manager Copilot" en el
handshake `initialize`, tal y como exige el encargo.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server

logger = logging.getLogger("mcp_server.transport")

SERVER_NAME = "SOMA — Smart Manager Copilot"
SERVER_VERSION = "1.0.0"

MCP_SESSION_HEADER = "Mcp-Session-Id"

server: Server = Server(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "SOMA es el copiloto de Smart Manager. Expone herramientas de solo lectura y, en el "
        "futuro, acciones de negocio que SIEMPRE se enrutan como propuestas sujetas a aprobación "
        "humana (Workflow/Gobierno) — nunca ejecución directa."
    ),
)


@server.list_tools()
async def _handle_list_tools() -> list[types.Tool]:
    from src.mcp_server.registry import listar_tools
    return [types.Tool(name=t["nombre"], description=t["descripcion"], inputSchema=t["schema"])
            for t in listar_tools()]


@server.call_tool()
async def _handle_call_tool(name: str, arguments: dict):
    import json

    from src.mcp_server.registry import ejecutar_tool
    # Cualquier excepción (tool desconocida, sin contexto, error de negocio) la captura el propio
    # decorador `@server.call_tool()` del SDK y la convierte en `CallToolResult(isError=True, ...)`
    # — no hace falta un try/except aquí (ver `mcp.server.lowlevel.server.Server.call_tool`).
    resultado = ejecutar_tool(name, arguments or {})
    return [types.TextContent(type="text", text=json.dumps(resultado, ensure_ascii=False))]


def _negociar_version(solicitada) -> str:
    from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
    if solicitada in SUPPORTED_PROTOCOL_VERSIONS:
        return solicitada
    return types.LATEST_PROTOCOL_VERSION


def _run(coro):
    """Ejecuta una corrutina en un event-loop NUEVO y autocontenido — una por petición HTTP (ver
    docstring del módulo, opción (c)). Sin estado de `asyncio` compartido entre peticiones."""
    return asyncio.run(coro)


def _resultado_jsonrpc(id_, result_model) -> dict:
    return {"jsonrpc": "2.0", "id": id_,
            "result": result_model.model_dump(by_alias=True, exclude_none=True, mode="json")}


def _error_jsonrpc(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _registrar_actividad_tool_call(nombre_tool: str, result) -> None:
    """Traza MÍNIMA y best-effort de cada `tools/call` real (una llamada externa de ChatGPT/Claude
    Desktop vía MCP) — para que el escritorio pueda avisar "petición MCP procesada" sin inventar un
    motor de eventos/tabla nuevo: reutiliza `db.conexion.log_auditoria` (la MISMA `auditoria_logs`
    que ya usa el resto del sistema) bajo `tabla_afectada='mcp'`, que `db.auditoria.listar_por_tabla`
    ya sabe leer (Fase 3 · cliente fino de auditoría). Cero tablas/endpoints nuevos. El tenant se fija
    EXPLÍCITAMENTE con `contexto_tenant` (la empresa del JWT de la llamada, nunca el contexto
    global/hilo que ya pueda haber) porque este endpoint no pasa por `requiere_auth`/`g.ctx`."""
    try:
        from src.mcp_server.registry import obtener_contexto_actual
        ctx = obtener_contexto_actual() or {}
        id_empresa = ctx.get("id_empresa")
        if not id_empresa:
            return
        usuario = (ctx.get("usuario") or {}).get("nombre") or "mcp"
        # `result` es un `mcp.types.ServerResult` (RootModel): `isError` vive en `.root`, NO en el
        # propio `ServerResult` — `getattr(result, "isError", False)` fallaba SIEMPRE a False (bug
        # real encontrado al escribir la suite de regresión permanente de MCP). `.root` puede no
        # tener `isError` (p.ej. en `initialize`/`tools/list`, que no son CallToolResult) — de ahí
        # el getattr anidado, honesto en ambos casos.
        es_error = bool(getattr(getattr(result, "root", None), "isError", False))
        from src.db.conexion import log_auditoria
        from src.db.empresa import contexto_tenant
        with contexto_tenant(id_empresa):
            log_auditoria(str(usuario)[:80], f"MCP_TOOL_CALL:{nombre_tool}"[:80], "mcp",
                          f"tool={nombre_tool} error={es_error}"[:255])
    except Exception as e:
        logger.debug("auditoría MCP tool-call no registrada: %s", e)


def _procesar_mensaje(msg: dict) -> dict | None:
    """Despacha UN mensaje JSON-RPC (request o notification). Devuelve `None` para las
    notifications (no llevan respuesta) o el dict de respuesta JSON-RPC para las requests."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not msg.get("method"):
        return _error_jsonrpc(msg.get("id") if isinstance(msg, dict) else None,
                              types.INVALID_REQUEST, "Mensaje JSON-RPC inválido")
    metodo = msg["method"]
    id_ = msg.get("id")
    es_notificacion = "id" not in msg
    params = msg.get("params") or {}

    try:
        if metodo == "initialize":
            protocolo = _negociar_version(params.get("protocolVersion"))
            init_opts = server.create_initialization_options(NotificationOptions())
            result = types.InitializeResult(
                protocolVersion=protocolo,
                capabilities=init_opts.capabilities,
                serverInfo=types.Implementation(name=server.name, version=server.version),
                instructions=server.instructions,
            )
            return _resultado_jsonrpc(id_, result)

        if metodo == "notifications/initialized":
            return None   # confirmación del cliente; nada que responder (modo stateless)

        if metodo == "ping":
            return _resultado_jsonrpc(id_, types.EmptyResult())

        if metodo == "tools/list":
            handler = server.request_handlers.get(types.ListToolsRequest)
            req = types.ListToolsRequest(method="tools/list")
            result = _run(handler(req))
            return _resultado_jsonrpc(id_, result)

        if metodo == "tools/call":
            if "name" not in params:
                return _error_jsonrpc(id_, types.INVALID_PARAMS, "Falta 'name' en params")
            handler = server.request_handlers.get(types.CallToolRequest)
            req = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name=params["name"], arguments=params.get("arguments")),
            )
            result = _run(handler(req))
            _registrar_actividad_tool_call(params["name"], result)
            return _resultado_jsonrpc(id_, result)

        if es_notificacion:
            return None   # notification de un método que no manejamos: se ignora, no es error

        return _error_jsonrpc(id_, types.METHOD_NOT_FOUND, f"Método no soportado: {metodo}")

    except Exception as e:
        logger.exception("Error despachando método MCP '%s'", metodo)
        if es_notificacion:
            return None
        return _error_jsonrpc(id_, types.INTERNAL_ERROR, "Error interno procesando la petición")


def _resource_metadata_url() -> str:
    from flask import request
    return request.host_url.rstrip("/") + "/.well-known/oauth-protected-resource"


def crear_blueprint():
    """Blueprint Flask con el único endpoint `/mcp` (Streamable HTTP, modo sin sesión servidor:
    ver docstring del módulo). Protegido con el MISMO contexto JWT/API-Key que la REST API
    (`src.api.security.contexto_de_request`) — un MCP access token es, bit a bit, el mismo JWT
    que emite `seguridad.tokens`, así que la validación es literalmente la misma función."""
    from flask import Blueprint, jsonify, request

    bp = Blueprint("mcp_transport", __name__)

    @bp.post("/mcp")
    def mcp_endpoint():
        from src.api.security import contexto_de_request
        from src.mcp_server.registry import fijar_contexto_actual, limpiar_contexto_actual

        ctx = contexto_de_request()
        if not ctx or not ctx.get("id_empresa"):
            resp = jsonify({"error": "unauthorized"})
            resp.status_code = 401
            resp.headers["WWW-Authenticate"] = (
                f'Bearer realm="SOMA", resource_metadata="{_resource_metadata_url()}"')
            return resp

        cuerpo = request.get_json(silent=True)
        if cuerpo is None:
            return jsonify(_error_jsonrpc(None, types.PARSE_ERROR, "Cuerpo JSON inválido")), 400

        es_lote = isinstance(cuerpo, list)
        mensajes = cuerpo if es_lote else [cuerpo]

        fijar_contexto_actual(ctx)
        try:
            respuestas = [r for r in (_procesar_mensaje(m) for m in mensajes) if r is not None]
        finally:
            limpiar_contexto_actual()

        sesion_id = request.headers.get(MCP_SESSION_HEADER) or str(uuid.uuid4())
        if not respuestas:
            # Solo notifications: 202 Accepted sin cuerpo (igual que el transporte de referencia).
            resp = ("", 202)
            from flask import make_response
            r = make_response(resp)
            r.headers[MCP_SESSION_HEADER] = sesion_id
            return r

        resp = jsonify(respuestas if es_lote else respuestas[0])
        resp.headers[MCP_SESSION_HEADER] = sesion_id
        return resp

    @bp.get("/mcp")
    def mcp_endpoint_get():
        # Streaming SSE servidor→cliente NO soportado en este scaffold (ver docstring del
        # módulo) — degradación HONESTA (405), nunca una respuesta inventada.
        return jsonify({"error": "sse_not_supported",
                        "detalle": "Este servidor solo soporta POST /mcp (modo sin sesión)."}), 405

    @bp.delete("/mcp")
    def mcp_endpoint_delete():
        from src.api.security import contexto_de_request
        ctx = contexto_de_request()
        if not ctx or not ctx.get("id_empresa"):
            return jsonify({"error": "unauthorized"}), 401
        # Sin sesión de servidor que terminar (modo stateless) — 204 no-op, válido por spec.
        return ("", 204)

    return bp


__all__ = ["server", "crear_blueprint", "SERVER_NAME", "SERVER_VERSION"]
