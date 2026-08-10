# Changelog — SDK de JavaScript (@smartmanager/sdk)

Sigue [SemVer](https://semver.org/lang/es/).

## [1.0.0] — 2026-07-18

### Añadido
- Cliente inicial de la Enterprise REST API v1 (`Client`, `Resource`, `SmartManagerError`).
- Autenticación por JWT (`token`) y por API Key (`apiKey` + `empresa`).
- Recursos oficiales: communications, conversations, templates, campaigns, contacts, audit, commerce,
  system.
- Convención de paginación/orden/filtrado e iteración por cursor (`paginate`, async iterator).
- Basado en `fetch` (Node 18+ / navegador), sin dependencias; transporte inyectable.
- Empaquetado npm (`package.json`, ESM).
