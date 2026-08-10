# RUNBOOK — TIEMPO REAL EN RED (SSE)

## Endpoints
- `GET /api/v1/realtime/stream[?canales=stock,ventas]` — flujo SSE (`text/event-stream`). Requiere
  `Authorization: Bearer <JWT>`. El tenant sale del token. Eventos: `event: <tipo>`, `id: <uuid>`,
  `data: <json>`. Heartbeat `: ping` cada 15 s.
- `GET /api/v1/realtime/metrics` — conexiones totales/activas, eventos repartidos, descartes, conexiones del
  tenant. Requiere JWT.

## Consumir desde un módulo/app (cliente reutilizable)
```python
from src.services.eventbus.realtime_client import RealtimeClient
cli = RealtimeClient("https://api.tudominio.com", token_provider=lambda: mi_jwt(),
                     canales=["stock", "ventas"], on_event=lambda ev: refrescar(ev))
cli.connect()      # hilo en segundo plano; reconexión por backoff exponencial; reautentica en cada intento
# ...
cli.disconnect()
```

## Publicar un evento (que llegará en tiempo real)
Usar el Event Bus EXISTENTE — NO publicar directo al transporte:
```python
from src.services.eventbus import publish
publish("stock.salida", id_empresa=emp, id_tienda=tnd)   # el hub lo reparte a los clientes del tenant
```

## Operación
- **Escalado horizontal:** con >1 instancia, cada instancia solo reparte los eventos publicados en su
  proceso. Para difundir entre instancias hace falta un broker distribuido → `realtime.set_distribucion()`
  (Redis/NATS) — **[EXTERNO], no activado**. Con 1 instancia funciona sin más.
- **Proxy/nginx:** deshabilitar buffering para SSE (`X-Accel-Buffering: no` ya se envía; en nginx
  `proxy_buffering off` para la ruta). Timeouts de proxy ≥ heartbeat.
- **Balanceador:** afinidad de sesión (sticky) recomendable para SSE en multi-instancia.

## Reconexión / estado
Tras una desconexión el cliente reconecta, **reautentica** (nuevo token del `token_provider`) y re-suscribe.
Los eventos perdidos durante la caída NO se reenvían por el stream → el cliente debe **resincronizar** el
estado con una consulta REST normal al reconectar (el stream es para actualizaciones incrementales).

## Observabilidad
`/realtime/metrics` + logs (nunca tokens/secretos). Integrable con la observabilidad existente.

## Diagnóstico
- 401 → token ausente/expirado/ inválido. 
- Sin eventos → ¿el `id_empresa` del token coincide con el del evento? ¿el canal está suscrito? ¿el proxy
  bufferiza? 
- Cliente "lento" (cola llena) → se descartan eventos (métrica `descartes_cola_llena`); resincronizar.
