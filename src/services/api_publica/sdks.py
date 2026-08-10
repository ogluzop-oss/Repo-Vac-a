"""
API Pública · SDKs (Fase V · Bloque 3 + Etapa E · Fase E3). Descriptores y METADATA de los SDK
oficiales para terceros. Los SDK se GENERAN desde el OpenAPI de la REST API (fuente única): aquí se
declaran los lenguajes soportados, un snippet de arranque por lenguaje y la metadata de empaquetado
(pip/npm) versionada. Los paquetes distribuibles reales viven en `sdk/python` y `sdk/javascript`
(mismo `VERSION`, fuente OpenAPI). No duplica la API.
"""

from __future__ import annotations

# Versión ÚNICA de los SDK oficiales (fuente de verdad; los paquetes pip/npm la declaran igual).
VERSION = "1.0.0"

LENGUAJES = ("python", "javascript", "typescript", "csharp", "java", "php")

# Lenguajes con paquete distribuible real (pip/npm) generado en esta fase.
DISTRIBUIBLES = ("python", "javascript")

# Metadata de empaquetado por lenguaje (nombre del paquete + gestor + ruta del artefacto).
_PAQUETES = {
    "python": {"paquete": "smartmanager", "gestor": "pip", "ruta": "sdk/python",
               "manifest": "pyproject.toml", "import": "smartmanager"},
    "javascript": {"paquete": "@smartmanager/sdk", "gestor": "npm", "ruta": "sdk/javascript",
                   "manifest": "package.json", "import": "@smartmanager/sdk"},
}

_SNIPPETS = {
    "python": ('from smartmanager import Client\n'
               'c = Client(base_url="https://api.tu-dominio/api/v1", token=ACCESS)\n'
               'c.communications.list(limite=20)'),
    "javascript": ('import { Client } from "@smartmanager/sdk";\n'
                   'const c = new Client({ baseUrl, token });\n'
                   'await c.communications.list({ limite: 20 });'),
    "typescript": ('import { Client } from "@smartmanager/sdk";\n'
                   'const c = new Client({ baseUrl, token });\n'
                   'const r = await c.communications.list({ limite: 20 });'),
    "csharp": ('var c = new SmartManager.Client(baseUrl, token);\n'
               'await c.Communications.ListAsync(limite: 20);'),
    "java": ('SmartManagerClient c = new SmartManagerClient(baseUrl, token);\n'
             'c.communications().list(20);'),
    "php": ('$c = new SmartManager\\Client($baseUrl, $token);\n'
            '$c->communications->list(["limite" => 20]);'),
}


def lenguajes() -> tuple:
    return LENGUAJES


def snippet(lenguaje) -> str:
    return _SNIPPETS.get(lenguaje, "")


def paquete(lenguaje) -> dict | None:
    """Metadata de empaquetado (pip/npm) de un SDK distribuible, o None si el lenguaje no tiene
    paquete real generado. Incluye la `VERSION` única."""
    meta = _PAQUETES.get(lenguaje)
    if not meta:
        return None
    return {**meta, "version": VERSION}


def metadata(lenguaje=None) -> dict:
    """Metadata de los SDK oficiales. Sin argumento devuelve la global (versión + distribuibles); con
    un lenguaje, su metadata de empaquetado. Fuente de la API: OpenAPI (recursos derivados)."""
    if lenguaje:
        return paquete(lenguaje) or {}
    recursos = []
    try:
        from src.services.api_publica import openapi_publica
        recursos = openapi_publica.recursos()
    except Exception:
        pass
    return {"version": VERSION, "lenguajes": list(LENGUAJES),
            "distribuibles": list(DISTRIBUIBLES), "fuente": "openapi",
            "paquetes": {l: paquete(l) for l in DISTRIBUIBLES}, "recursos_api": recursos}


def descriptor() -> dict:
    return {"version": VERSION, "lenguajes": list(LENGUAJES),
            "distribuibles": list(DISTRIBUIBLES), "fuente": "openapi",
            "generacion": "automatica_desde_openapi",
            "snippets": {l: _SNIPPETS[l] for l in LENGUAJES}}


__all__ = ["VERSION", "LENGUAJES", "DISTRIBUIBLES", "lenguajes", "snippet", "paquete", "metadata",
           "descriptor"]
