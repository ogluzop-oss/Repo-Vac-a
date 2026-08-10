# Smart Manager AI — SDK de JavaScript

Cliente oficial de la **Enterprise REST API** (`/api/v1`) de Smart Manager AI. Usa `fetch` (Node 18+ o
navegador), sin dependencias.

## Instalación

```bash
npm install @smartmanager/sdk
```

## Uso

```javascript
import { Client } from "@smartmanager/sdk";

// Autenticación por JWT
const c = new Client({ baseUrl: "https://api.tu-dominio/api/v1", token: ACCESS_TOKEN });

// ...o por API Key (máquina a máquina)
const m = new Client({ baseUrl, apiKey: API_KEY, empresa: "EMP-123" });

// Listar con la convención de paginación/orden/filtrado
await c.communications.list({ limit: 20, sort: "fecha", order: "desc" });

// Iterar TODOS los elementos siguiendo el cursor automáticamente
for await (const contacto of c.contacts.paginate({ q: "ana" })) {
  console.log(contacto);
}

// Crear
await c.templates.create({ codigo: "bienvenida", asunto: "Hola", cuerpo: "..." });

// Salud
await c.health();
```

## Autenticación

- **JWT**: `new Client({ baseUrl, token })` → `Authorization: Bearer`.
- **API Key**: `new Client({ baseUrl, apiKey, empresa })` → `X-API-Key` + `X-Empresa-Id`.

## Paginación

`limit/offset/cursor/page/page_size/sort/order/filters`; la respuesta es un sobre
`{ data, total, next_cursor, ... }`. `paginate()` es un async iterator que sigue `next_cursor`.

## Fuente de verdad

OpenAPI de la API: `GET /api/v1/openapi.json` (Swagger en `/api/v1/docs`). El SDK no duplica la API.

Versión: **1.0.0** — ver [CHANGELOG](CHANGELOG.md).
