# ARQUITECTURA — EVENTOS MULTI-INSTANCIA (Fase 10)

## Principio

El Event Bus de dominio (`services.eventos.bus`) y el hub de tiempo real (`eventbus.realtime`) siguen siendo la
**única lógica de eventos**. La distribución multi-instancia es una **capa de transporte** que propaga el
evento serializado a otras réplicas ECS y entrega los remotos al hub local. **No es un segundo Event Bus.**

## Flujo

```
Evento de dominio → bus.publicar → realtime._on_event(ev)         (instancia local)
        │                                   │
        │                          reparte a clientes SSE del MISMO tenant
        ▼
  _DISTRIBUCION.publicar(ev)  ──(broker)──▶ otra instancia: realtime._on_event(ev, _remoto=True)
                                                   │
                                          reparte a SUS clientes SSE del MISMO tenant
```

- Eventos **locales** (`_remoto=False`) → se reparten localmente **y** se propagan al broker.
- Eventos **remotos** (`_remoto=True`) → sólo se reparten localmente, **no** se reenvían (evita bucles).

## Aislamiento por tenant (idéntico en single y multi-instancia)

El `id_empresa` viaja dentro del evento; el reparto filtra por tenant en ambos extremos. Un evento de Tenant A
**nunca** llega a un cliente de Tenant B, esté en la misma instancia o en otra. Verificado por tests
(`test_distribucion_reparto_aislado_por_tenant`, `test_inprocess_distribution_entrega_preserva_tenant`).

## Backends (`eventbus/distribucion.py`)

| Backend | Uso | Estado |
|---|---|---|
| `LocalDistribution` | single-instance (por defecto) | 🟢 |
| `InProcessDistribution` | tests deterministas (conecta hubs en el mismo proceso, JSON round-trip) | 🟢 |
| `RedisDistribution` | multi-instancia real (Redis Pub/Sub, boto3/redis perezoso) | 🔵 PREPARADO |

## Activación (cuando se escale SSE)

```python
from src.services.eventbus import realtime
from src.services.eventbus.distribucion import RedisDistribution
d = RedisDistribution(entregar_remoto=lambda ev: realtime._on_event(ev, _remoto=True))
d.iniciar(); realtime.set_distribucion(d)
```

Requiere `REALTIME_BROKER_URL` (ElastiCache Redis) — 🟣 externo. Sin broker, el hub opera single-instance.
Redis es SÓLO transporte de distribución SSE (los jobs van por SQS, el dominio por el Event Bus).
