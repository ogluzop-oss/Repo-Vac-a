# ARQUITECTURA — SSE EN AWS (Fase 10, implementación)

Complementa `AUDITORIA_SSE_AWS.md` (Fase 9) con lo IMPLEMENTADO.

## Cambio implementado: worker asíncrono

`gunicorn.conf.py` fija `worker_class = gevent` (configurable). Con workers **gevent**, cada conexión SSE
(`/api/v1/realtime/stream`, `while True` + heartbeat 15 s) NO bloquea un worker: soporta miles de conexiones
concurrentes sin afectar a las peticiones HTTP normales. El Dockerfile arranca con `gunicorn -c gunicorn.conf.py`.

## Parámetros para ALB / CloudFront

| Parámetro | Valor | Motivo |
|---|---|---|
| `GUNICORN_WORKER_CLASS` | `gevent` | conexiones largas SSE |
| `keepalive` | 75 s | > idle timeout típico de ALB |
| `timeout` | 120 s | no matar conexiones SSE (heartbeat 15 s las mantiene) |
| ALB idle timeout | > 15 s | el heartbeat evita el corte |
| CloudFront | política SSE sin buffer, reenviar `Authorization` | `text/event-stream` no cacheable |

## Se conserva (sin cambios)

JWT, autenticación, **aislamiento por tenant** (el `id_empresa` sale del token), RBAC, rate limiting,
heartbeat, reconexión, canales, cierre limpio. Endpoint sigue en `/realtime/stream`. Múltiples clientes
concurrentes soportados por el worker async.

## Multi-instancia

1 instancia → funciona sin broker. N instancias → ver `ARQUITECTURA_EVENTOS_MULTI_INSTANCE.md`
(distribución Redis 🔵). Estado: 🟢 SSE AWS-ready (worker async); 🔵 multi-instancia (broker externo).
