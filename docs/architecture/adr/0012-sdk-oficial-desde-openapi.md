# ADR-0012: SDK oficial distribuible desde OpenAPI (E3)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (Etapa E · Fase E3)

## Contexto

`api_publica/sdks.py` declaraba lenguajes y snippets, pero no existía un paquete cliente distribuible.

## Decisión

Se publican SDK cliente oficiales para **Python** (`smartmanager`, pip) y **JavaScript**
(`@smartmanager/sdk`, npm) en `sdk/python` y `sdk/javascript`:

- clientes reales, ligeros y sin dependencias obligatorias (urllib / fetch), con transporte inyectable;
- autenticación JWT/API Key; soporte de la convención de paginación (ADR-0010) e iteración por cursor;
- **fuente de verdad = OpenAPI** (`/api/v1/openapi.json`); el SDK no duplica la lógica de la API;
- **versión única** en `api_publica.sdks.VERSION`, coincidente con `pyproject.toml`/`package.json`;
- CHANGELOG, metadata, documentación y ejemplos por paquete.

## Consecuencias

- (+) Integración de terceros sencilla y versionada (SemVer).
- (−) Los clientes exponen los recursos actuales de la API v1 (ampliables aditivamente); generación
  automática total desde OpenAPI queda como mejora.
