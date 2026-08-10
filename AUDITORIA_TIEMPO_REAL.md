# AUDITORÍA — TIEMPO REAL EN RED (Fase 4)

Auditoría previa (Fase 0), en modo lectura, del estado de tiempo real antes de implementar.

## Event Bus (existente, real)
- `services/eventbus` (facade): `publish(tipo, id_empresa, id_tienda, …)`, `subscribe(tipo, handler)`,
  `unsubscribe`, `replay`, `catalogo`. Sobre `services/eventos/bus`.
- `services/eventos/bus.publicar`: crea un `Evento` (con `uuid`, `tipo`, `id_empresa`, `id_tienda`,
  `to_dict()`), lo **persiste** en `eventos` y **`_notificar_suscriptores(ev)`** avisa a los suscriptores
  in-process (por `tipo` y por comodín `"*"`), pasándoles `ev.to_dict()`. **Pub/sub in-process REAL y
  síncrono** (no polling).
- `subscription_manager` lleva el registro de suscripciones.

## API (existente)
- Flask, blueprint versionado `/api/v1` (`src/api`), routers en `src/api/routers/*` (cada uno
  `registrar(bp)`). Autenticación `requiere_auth` (`src/api/security`): JWT → `contexto_de_request` →
  **tenant SIEMPRE del token** (`g.ctx["id_empresa"]`), 401 si no autenticado; RBAC vía `autorizacion.puede`;
  rate limiting integrado. API keys M2M separadas del MFA humano.

## Tiempo real previo
- `api/graphql/subscriptions.py`: declara canales pero **"No abre websockets ni push todavía"**.
- **No existía** transporte SSE/WebSocket que empujara eventos a clientes de red. → esta es la brecha.

## Seguridad / tenant
- `seguridad/tenant_guard`, aislamiento por `id_empresa` transversal, RBAC. Reutilizables para autorizar
  conexiones y suscripciones.

## Conclusión
Existe un Event Bus in-process **real** con pub/sub. **Falta el transporte de red** (server→cliente). Se
puede implementar SIN infraestructura externa mediante **SSE** (respuesta HTTP `text/event-stream` en el
Flask existente), consumiendo el bus real y reutilizando JWT + aislamiento por tenant. Multi-instancia
(broker distribuido) sí requiere infra externa → punto de extensión, no simulado.
