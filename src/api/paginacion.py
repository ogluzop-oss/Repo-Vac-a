"""
Convención uniforme de paginación / ordenación / filtrado para la Enterprise REST API (Fase E1).

ADITIVO y 100 % RETROCOMPATIBLE (Reglas 3/6/7/10): no crea una API nueva ni toca los servicios/dominio.
Opera sobre la lista que el router YA obtiene del servicio. Si el cliente NO usa los parámetros nuevos,
la respuesta es IDÉNTICA a la actual (lista JSON simple) — no se rompe ningún contrato. Si el cliente
SÍ los usa (`limit`/`offset`/`cursor`/`page`/`page_size`/`sort`/`order`/`filters`/`paginated`), se
devuelve un sobre estándar:

    {"data": [...], "total": N, "count": k, "limit": L, "offset": O, "page": P,
     "page_size": PS, "sort": campo, "order": "asc|desc", "next_cursor": "..."|null}

Los parámetros LEGACY existentes (`limite`, `q`, `estado`, `canal`, ...) se conservan tal cual: `limite`
(castellano) NO activa el sobre; `limit` (nuevo) sí. Reutiliza `flask.request`; no accede a la BD.
"""

from __future__ import annotations

import base64
import json
import logging

logger = logging.getLogger("api.paginacion")

# Parámetros que ACTIVAN la convención (su mera presencia opta por el sobre estándar).
PARAMS = ("limit", "offset", "cursor", "page", "page_size", "sort", "order", "filters", "paginated")

_LIMIT_DEFECTO = 100
_LIMIT_MAX = 500


def _int(valor, defecto=None):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _cursor_encode(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": int(offset)}).encode()).decode()


def _cursor_decode(cursor: str) -> int:
    try:
        return int(json.loads(base64.urlsafe_b64decode(str(cursor).encode()).decode()).get("o", 0))
    except Exception:
        return 0


def parametros(args=None) -> dict:
    """Extrae y normaliza los parámetros de la convención desde `request.args` (o un dict/MultiDict).
    `activo` indica si el cliente ha solicitado la convención (algún parámetro nuevo presente)."""
    if args is None:
        try:
            from flask import request
            args = request.args
        except Exception:
            args = {}

    def _get(k, d=None):
        try:
            return args.get(k, d)
        except AttributeError:
            return (args or {}).get(k, d)

    claves = list(args.keys()) if hasattr(args, "keys") else list(args)
    activo = any(k in claves for k in PARAMS) or any(
        isinstance(k, str) and k.startswith("filter[") and k.endswith("]") for k in claves)

    page = _int(_get("page"))
    page_size = _int(_get("page_size"))
    limit = _int(_get("limit"))
    offset = _int(_get("offset"), 0) or 0
    cursor = _get("cursor")

    if page_size:
        limit = page_size
    if page and page_size:
        offset = max(0, (page - 1) * page_size)
    if cursor:
        offset = _cursor_decode(cursor)
    if limit is None:
        limit = _LIMIT_DEFECTO
    limit = max(1, min(limit, _LIMIT_MAX))
    offset = max(0, offset)

    # filtros: JSON en `filters` y/o pares `filter[campo]=valor`.
    filtros: dict = {}
    crudo = _get("filters")
    if crudo:
        try:
            val = json.loads(crudo)
            if isinstance(val, dict):
                filtros.update(val)
        except Exception:
            logger.debug("filters no es JSON válido: %r", crudo)
    for k in claves:
        if isinstance(k, str) and k.startswith("filter[") and k.endswith("]"):
            filtros[k[7:-1]] = _get(k)

    order = str(_get("order") or "asc").lower()
    if order not in ("asc", "desc"):
        order = "asc"

    return {"activo": activo, "limit": limit, "offset": offset, "cursor": cursor,
            "page": page, "page_size": page_size, "sort": _get("sort"),
            "order": order, "filters": filtros}


def _valor(item, campo):
    if isinstance(item, dict):
        return item.get(campo)
    return getattr(item, campo, None)


def _coincide(valor, criterio) -> bool:
    if valor is None:
        return False
    return str(criterio).lower() in str(valor).lower()


def aplicar(items, params: dict):
    """Aplica filtrado → orden → recorte sobre la lista dada. Devuelve `(pagina, total)`. `total` es el
    nº de elementos tras el filtrado (antes de recortar). No muta la lista de entrada."""
    datos = list(items or [])
    for campo, criterio in (params.get("filters") or {}).items():
        datos = [d for d in datos if _coincide(_valor(d, campo), criterio)]
    total = len(datos)

    sort = params.get("sort")
    if sort:
        rev = params.get("order") == "desc"
        try:
            datos = sorted(datos, key=lambda d: (_valor(d, sort) is None, _valor(d, sort)), reverse=rev)
        except TypeError:
            datos = sorted(datos, key=lambda d: str(_valor(d, sort)), reverse=rev)

    offset = params.get("offset", 0) or 0
    limit = params.get("limit")
    pagina = datos[offset: offset + limit] if limit else datos[offset:]
    return pagina, total


def envolver(items, params: dict | None = None):
    """Punto de entrada para los routers. Si la convención NO está activa devuelve `items` sin cambios
    (retrocompatible). Si está activa devuelve el sobre estándar. `items` debe ser una lista ya
    serializable (p. ej. `[d.to_dict() for d in res]`)."""
    if params is None:
        params = parametros()
    if not params.get("activo"):
        return items
    pagina, total = aplicar(items, params)
    offset, limit = params["offset"], params["limit"]
    hay_mas = (offset + len(pagina)) < total
    page = params.get("page") or ((offset // limit) + 1 if limit else 1)
    return {"data": pagina, "total": total, "count": len(pagina),
            "limit": limit, "offset": offset, "page": page,
            "page_size": params.get("page_size") or limit,
            "sort": params.get("sort"), "order": params.get("order"),
            "next_cursor": _cursor_encode(offset + limit) if hay_mas else None}


# Descriptor OpenAPI de los parámetros de la convención (reutilizado por `openapi.py`).
def openapi_parametros() -> list:
    q = "query"
    return [
        {"name": "limit", "in": q, "required": False, "schema": {"type": "integer"},
         "description": "Máximo de elementos (activa el sobre de paginación estándar)."},
        {"name": "offset", "in": q, "required": False, "schema": {"type": "integer"}},
        {"name": "cursor", "in": q, "required": False, "schema": {"type": "string"},
         "description": "Cursor opaco devuelto en `next_cursor`."},
        {"name": "page", "in": q, "required": False, "schema": {"type": "integer"}},
        {"name": "page_size", "in": q, "required": False, "schema": {"type": "integer"}},
        {"name": "sort", "in": q, "required": False, "schema": {"type": "string"},
         "description": "Campo por el que ordenar."},
        {"name": "order", "in": q, "required": False,
         "schema": {"type": "string", "enum": ["asc", "desc"]}},
        {"name": "filters", "in": q, "required": False, "schema": {"type": "string"},
         "description": "Filtros como JSON (`{\"campo\":\"valor\"}`) o pares `filter[campo]=valor`."},
    ]


__all__ = ["PARAMS", "parametros", "aplicar", "envolver", "openapi_parametros"]
