# API REST — Smart Manager AI (A1)

Capa de exposición HTTP **fina** sobre los servicios existentes (la lógica de
negocio NO se duplica en los endpoints). Servida por el backend Flask
(`src/backend/app.py` → blueprint `src/backend/api.py`). Server-side: el `.exe` de
escritorio NO la lanza.

## Versionado

- Prefijo **estable** `/api/v1`. Todos los endpoints cuelgan de ahí.
- **Evolución sin romper clientes:** un cambio incompatible se publica como un
  **nuevo blueprint `/api/v2`** que **convive** con `/api/v1`; `v1` se mantiene
  durante un periodo de deprecación anunciado. Los cambios compatibles (añadir
  campos/endpoints) se hacen dentro de `v1`. Cada versión es un blueprint propio
  (`crear_blueprint_api`), por lo que añadir `v2` no toca `v1`.

## Autenticación (JWT)

- `POST /api/v1/auth/login` — body `{usuario|email, password, empresa?}` →
  `{access, refresh, usuario}`. `access` ~15 min; `refresh` ~30 días, **revocable**
  (persistido *hasheado* en `sesiones`).
- `POST /api/v1/auth/refresh` — `{refresh}` → `{access}` (recarga el usuario para
  reflejar rol/tienda actuales; valida que el refresh no esté revocado/caducado).
- `POST /api/v1/auth/logout` — `{refresh}` → revoca la sesión.
- `GET /api/v1/auth/me` — (protegido) datos del usuario del token.
- Cabecera de acceso: `Authorization: Bearer <access>`.

## Aislamiento multi-tenant (A4)

El decorador `@token_requerido` valida el token y fija el **`TenantContext` del
hilo** (empresa/tienda/rol) desde los *claims*, restaurándolo al terminar la
petición. Es **thread-local** → bajo concurrencia cada petición opera SOLO en su
tenant; imposible fuga entre empresas. El escritorio sigue usando el contexto
global (sin cambios).

## Recursos (solo lectura, A1.2)

- `GET /api/v1/catalogo/productos?categoria=&marca=&texto=&limite=` — vista
  pública u operativa según el rol; aislado por empresa.
- `GET /api/v1/catalogo/productos/<id>`
- `GET /api/v1/catalogo/categorias`
- `GET /api/v1/pedidos?estado=` — pedidos del tenant del token.
- `GET /api/v1/pedidos/<id>` — 404 si el pedido no pertenece al tenant (aislamiento).

## CORS (configurable por entorno)

- Lista blanca en `API_CORS_ORIGINS` (orígenes separados por coma). **Nunca `*`.**
- Vacío = sin CORS (solo mismo origen). En producción, fijar únicamente los
  dominios reales (app móvil/web propia/integraciones autorizadas).
- Preflight `OPTIONS` → 204; las respuestas añaden las cabeceras solo si el `Origin`
  está en la lista blanca.

## Ejecutar el backend (server-side)

```bash
python -m src.backend.app      # BACKEND_HOST / BACKEND_PORT (o PORT) por entorno
```

## Seguridad operativa (A5)

- **Secretos por entorno con fail-fast (A5.1):** con `SMART_MANAGER_ENV=prod`, el
  backend **no arranca** sin `SMART_MANAGER_JWT_SECRET` ni clave maestra por entorno
  (`validar_arranque_seguro`); en desarrollo solo avisa. `tokens` nunca usa el secreto
  de desarrollo en producción.
- **Rate limiting (A5.2):** por IP+endpoint, backend **enchufable** (`rate_limit.py`,
  en memoria por defecto; `set_backend()` para Redis en SaaS multi-instancia). Aplicado
  a `auth/login` (10/min), `auth/refresh` y `auth/logout` (30/min) → `429` al exceder.
- **No-exposición (A4.2/A5.3):** lista blanca por recurso + red `_sin_secretos`; tests
  que verifican que la API nunca devuelve password/hash/api_key/secret/token ni
  credenciales en `catalogo`/`pedidos`/`me` (`auth/*` sí devuelve tokens, a propósito).

## Principios

- Endpoints = traducción HTTP↔servicio; toda la lógica vive en `src/services` y
  `src/db`. Secretos por el sistema de claves de C1 (la API nunca los devuelve).
