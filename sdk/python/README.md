# Smart Manager AI — SDK de Python

Cliente oficial de la **Enterprise REST API** (`/api/v1`) de Smart Manager AI. Sin dependencias
obligatorias (usa `urllib` de la biblioteca estándar).

## Instalación

```bash
pip install smartmanager
```

## Uso

```python
from smartmanager import Client

# Autenticación por JWT
c = Client("https://api.tu-dominio/api/v1", token=ACCESS_TOKEN)

# ...o por API Key (máquina a máquina)
c = Client("https://api.tu-dominio/api/v1", api_key=API_KEY, empresa="EMP-123")

# Listar con la convención de paginación/orden/filtrado
c.communications.list(limit=20, sort="fecha", order="desc")

# Iterar TODOS los elementos siguiendo el cursor automáticamente
for contacto in c.contacts.paginate(q="ana"):
    print(contacto)

# Crear
c.templates.create({"codigo": "bienvenida", "asunto": "Hola", "cuerpo": "..."})

# Salud del servicio
c.health()
```

## Autenticación

- **JWT**: `Client(base_url, token=...)` → cabecera `Authorization: Bearer`.
- **API Key**: `Client(base_url, api_key=..., empresa=...)` → cabeceras `X-API-Key` + `X-Empresa-Id`.

El aislamiento por empresa (tenant) lo fija SIEMPRE el token/clave en el servidor.

## Paginación

La API soporta `limit`, `offset`, `cursor`, `page`, `page_size`, `sort`, `order`, `filters`. Cuando se
solicita, la respuesta es un sobre `{ data, total, page, page_size, next_cursor, ... }`. `paginate()`
itera transparentemente siguiendo `next_cursor`.

## Fuente de verdad

La especificación de la API es su **OpenAPI**: `GET /api/v1/openapi.json` (Swagger UI en `/api/v1/docs`).
Este SDK no duplica la lógica de la API.

Versión: **1.0.0** — ver [CHANGELOG](CHANGELOG.md).
