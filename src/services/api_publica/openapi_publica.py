"""
API Pública · OpenAPI (Fase V · Bloque 3). Expone el OpenAPI/Swagger de la REST API oficial como
FUENTE ÚNICA para el Portal Developer y los SDK. Reutiliza `src.api.openapi` (no redefine la API):
la especificación se sirve desde el propio blueprint REST (`/api/v1/openapi.json`). Aquí se ofrece
un acceso en proceso al documento para documentación/generación de SDK.
"""

from __future__ import annotations


def documento(url_prefix="/api/v1") -> dict:
    """Devuelve el documento OpenAPI de la REST API (reutiliza el generador oficial)."""
    try:
        from src.api import openapi as _oa
        if hasattr(_oa, "_spec"):
            return _oa._spec(url_prefix)
    except Exception:
        pass
    # Degradable: descriptor mínimo si el generador no está disponible.
    return {"openapi": "3.0.0", "info": {"title": "Smart Manager AI API", "version": "1.0.0"},
            "servers": [{"url": url_prefix}], "paths": {}}


def swagger_url(url_prefix="/api/v1") -> str:
    return f"{url_prefix}/openapi.json"


def recursos() -> list:
    """Recursos públicos documentados (derivados del OpenAPI)."""
    doc = documento()
    return sorted((doc.get("paths") or {}).keys())


__all__ = ["documento", "swagger_url", "recursos"]
