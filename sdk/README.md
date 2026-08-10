# Smart Manager AI — SDKs oficiales

SDKs cliente para la **Enterprise REST API** (`/api/v1`). Ambos consumen la API existente; la **fuente
de verdad** es su OpenAPI (`GET /api/v1/openapi.json`, Swagger UI en `/api/v1/docs`). Los SDK no
duplican la lógica de negocio: solo transportan y traducen.

| Lenguaje | Paquete | Gestor | Ruta | Versión |
|----------|---------|--------|------|---------|
| Python | `smartmanager` | pip | [`sdk/python`](python/) | 1.0.0 |
| JavaScript | `@smartmanager/sdk` | npm | [`sdk/javascript`](javascript/) | 1.0.0 |

## Versionado

Los SDK siguen [SemVer](https://semver.org/lang/es/). La versión única se declara en
`src/services/api_publica/sdks.py` (`VERSION`) y coincide con la de cada paquete (`pyproject.toml` /
`package.json`). Cada paquete mantiene su propio `CHANGELOG.md`.

## Autenticación (común)

- **JWT** (`Authorization: Bearer`) — usuarios/sesiones.
- **API Key** (`X-API-Key` + `X-Empresa-Id`) — integraciones máquina a máquina.

El tenant (empresa) lo fija SIEMPRE el token/clave en el servidor (aislamiento estricto).

## Paginación / orden / filtrado

Ambos SDK soportan la convención estándar de la API (Etapa E · Fase E1):
`limit`, `offset`, `cursor`, `page`, `page_size`, `sort`, `order`, `filters`. Cuando se solicita, la
respuesta es un sobre `{ data, total, page, page_size, next_cursor, ... }`; los SDK ofrecen iteración
transparente por cursor (`paginate`).

## Publicación

- **pip**: `cd sdk/python && python -m build && twine upload dist/*`
- **npm**: `cd sdk/javascript && npm publish --access public`

## Recursos

communications · conversations · templates · campaigns · contacts · audit · commerce · system
(derivados del OpenAPI de la API v1).
