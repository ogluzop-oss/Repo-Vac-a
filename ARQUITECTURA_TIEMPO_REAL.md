# ARQUITECTURA — TIEMPO REAL EN RED

Transporte de tiempo real **server→cliente** por **SSE**, sobre el Event Bus EXISTENTE. Sin segundo bus, sin
segunda autenticación, sin dependencias nuevas (N7).

## Flujo real

```
Operación real (venta, salida de stock, OF, ticket SAT, NC calidad…)
        │  publica evento de dominio real
        ▼
services/eventos/bus.publicar  ──►  persiste en `eventos`  +  _notificar_suscriptores(ev.to_dict())
        │
        ▼
services/eventbus/realtime  (HUB, suscrito una vez a '*')
        │  reparte SOLO a clientes del MISMO id_empresa (aislamiento) y del canal suscrito
        ▼
GET /api/v1/realtime/stream  (SSE, text/event-stream, @requiere_auth)
        │  tenant = g.ctx["id_empresa"] (del TOKEN, nunca del cliente) · heartbeat 15s · cierre limpio
        ▼
RealtimeClient (services/eventbus/realtime_client)  — reutilizable por todos los módulos/apps
        │  connect / subscribe / reconnect(backoff) / on_event / on_error
        ▼
Actualización del componente afectado (TPV/Stock/CRM/Logística/Producción/GMAO/SAT/Calidad/Canal Web/móvil)
```

## Componentes (nuevos, mínimos)
| Componente | Rol | N7 |
|---|---|---|
| `services/eventbus/realtime.py` | HUB: puente 1:1 sobre el bus; colas por cliente; aislamiento por tenant; métricas | consume el bus existente |
| `api/routers/realtime.py` | Endpoint **SSE** `/realtime/stream` + `/realtime/metrics`; auth+tenant del token | reutiliza `requiere_auth` |
| `services/eventbus/realtime_client.py` | Cliente SSE reutilizable (connect/subscribe/reconnect/on_event) | único cliente, no por módulo |

## Canales
Derivados del `tipo` real del evento: canal = primer segmento (`stock.salida`→`stock`). Solo existen los que
corresponden a eventos reales publicados. Filtro opcional por `?canales=stock,ventas`.

## Seguridad
JWT obligatorio (401 sin token); tenant del token; aislamiento estricto por `id_empresa` (empresa A nunca
recibe eventos de empresa B); filtro de canal; heartbeat; cierre limpio (desregistro). Nunca se registran
tokens/secretos. Rate limiting heredado de `requiere_auth`.

## Escalabilidad
- **Single-instance:** operativo (event-driven, en memoria).
- **Multi-instancia:** requiere broker distribuido (Redis/NATS/…) → `realtime.set_distribucion(adaptador)`
  es el punto de extensión. **PREPARADO_PARA_DISTRIBUCION — [EXTERNO], no activado, no simulado.**
