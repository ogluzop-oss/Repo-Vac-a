"""
API Gateway (Fase IV · Bloque 3) — ABSTRACCIÓN. Punto único de entrada capaz de enrutar una
`Request` neutral hacia REST, GraphQL o (en el futuro) un microservicio, resolviendo el servicio
por Routing/Discovery, propagando auth+tracing y devolviendo una `Response`. NO abre puertos ni
implementa red: prepara la arquitectura para que, al distribuir, el enrutado no cambie.
"""

from __future__ import annotations

import time

from src.platform import discovery, routing
from src.platform.contracts import Request, Response

# Manejadores por transporte (se registran de forma perezosa/opcional).
_HANDLERS: dict = {}


def registrar_handler(transporte, fn):
    """Registra el ejecutor de un transporte: fn(servicio_contract, Request) -> datos."""
    _HANDLERS[transporte] = fn


def _handler_por_defecto(transporte):
    """Handlers integrados: 'graphql' delega en la capa GraphQL (que resuelve vía servicios)."""
    if transporte == "graphql":
        def _gql(_contrato, req: Request):
            from src.api.graphql import schema as _schema
            return _schema.ejecutar(req.operacion, req.args, contexto={
                "id_empresa": req.auth.id_empresa, "usuario": {
                    "id": req.auth.id_usuario, "perfil": req.auth.perfil,
                    "id_empresa": req.auth.id_empresa}})
        return _gql
    return None


def enrutar(req: Request) -> Response:
    """Resuelve el servicio para `req` y ejecuta el handler del transporte. Response neutral."""
    inicio = time.time()
    if req.transporte == "graphql":
        # Operación GraphQL (nombre de campo): la atiende el servicio 'graphql' (resuelve vía servicios).
        contrato = discovery.encontrar("graphql")
    else:
        contrato = routing.resolver(req.operacion, transporte=req.transporte) or \
            discovery.encontrar(req.operacion.split(".")[0])
    if contrato is None:
        return Response.fallo("no_route", f"sin servicio para '{req.operacion}'",
                              trace_id=req.tracing.trace_id)
    handler = _HANDLERS.get(req.transporte) or _handler_por_defecto(req.transporte)
    if handler is None:
        # Sin handler de red: el Gateway confirma el enrutado (preparación), sin ejecutar.
        return Response.exito({"enrutado_a": contrato.nombre, "transporte": req.transporte,
                               "ejecutado": False}, trace_id=req.tracing.trace_id,
                              ms=round((time.time() - inicio) * 1000, 2))
    try:
        datos = handler(contrato, req)
        return Response.exito(datos, trace_id=req.tracing.trace_id,
                              ms=round((time.time() - inicio) * 1000, 2))
    except Exception as e:
        return Response.fallo("handler_error", str(e), trace_id=req.tracing.trace_id)


__all__ = ["registrar_handler", "enrutar"]
