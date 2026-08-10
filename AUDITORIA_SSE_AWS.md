# AUDITORÍA — SSE / Tiempo real en AWS (Fase 9)

Objetivo: comportamiento del tiempo real (Event Bus → SSE) detrás de CloudFront/ALB/ECS. **No introducir
broker ni duplicar el Event Bus.**

## Estado actual (real)

- Endpoint `GET /api/v1/realtime/stream` (`api/routers/realtime.py`): `Response(mimetype="text/event-stream")`,
  `@stream_with_context`, bucle `while True` con **heartbeat cada 15 s** (`: ping\n\n`), autenticación JWT
  (`requiere_auth`), **tenant SIEMPRE del token** (aislamiento). `/realtime/metrics` para observabilidad.
- Transporte cliente: `RealtimeClient` (SSE, reconexión backoff) + puente Qt (`gui/realtime_qt`, Fase 8).
- **Event Bus in-process** (`services/eventbus`) — dispatch síncrono a suscriptores; hub por cliente con colas.

## Compatibilidad con la pila AWS

| Capa | Estado | Requisito |
|---|---|---|
| Worker gunicorn | 🟡 | **sync workers bloquean** con conexiones SSE largas → `--worker-class gevent`/`gthread` |
| ALB | 🟡 | idle timeout **> 15 s** (heartbeat lo mantiene vivo); target group con desregistro drenado |
| CloudFront | 🟡 | política de cache **deshabilitada** para `/api/v1/realtime/*`; NO bufferizar `text/event-stream`; reenviar `Authorization`; añadir `X-Accel-Buffering: no` en la respuesta |
| ECS 1 instancia | 🟢 | Event Bus in-process funciona: publish→hub→SSE→cliente, aislado por tenant (verificado en `test_realtime`) |
| ECS N instancias | 🟣 | un evento publicado en la instancia A no llega a un cliente SSE en la instancia B → requiere **broker** (Redis Pub/Sub / NATS / SNS) para fan-out entre instancias |
| WebSocket | 🔴/N/A | no implementado ni requerido (SSE cubre push server→cliente) |

## Recomendación honesta

- **Fase inicial AWS**: desplegar el servicio de tiempo real como **1 tarea** (o "sticky" por sesión SSE en el
  ALB) → funciona sin broker. Escalado horizontal de la API general con SSE en servicio dedicado.
- **Escalado real multi-instancia**: introducir un **broker** (🟣 externo) y una capa de distribución en el
  hub (`realtime.set_distribucion`, ya previsto como punto de extensión) — **en la fase de desarrollo, no ahora**.
- Añadir cabecera anti-buffering y ajustar timeouts en la definición de infraestructura.

**Veredicto: 🟢 SSE con 1 instancia · 🟡 requiere configuración (worker async + timeouts + no-buffer) · 🟣
multi-instancia requiere broker.** No duplicar el Event Bus; usar el punto de extensión existente.
