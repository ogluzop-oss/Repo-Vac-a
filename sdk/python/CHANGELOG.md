# Changelog — SDK de Python (smartmanager)

Todas las versiones notables de este SDK. Sigue [SemVer](https://semver.org/lang/es/).

## [1.0.0] — 2026-07-18

### Añadido
- Cliente inicial de la Enterprise REST API v1 (`Client`, `Resource`, `SmartManagerError`).
- Autenticación por JWT (`token`) y por API Key (`api_key` + `empresa`).
- Recursos oficiales: communications, conversations, templates, campaigns, contacts, audit, commerce,
  system.
- Soporte de la convención de paginación/orden/filtrado (`limit/offset/cursor/page/page_size/sort/
  order/filters`) e iteración por cursor (`paginate`).
- Cliente sin dependencias obligatorias (biblioteca estándar `urllib`); transporte inyectable.
- Empaquetado pip (`pyproject.toml`).
