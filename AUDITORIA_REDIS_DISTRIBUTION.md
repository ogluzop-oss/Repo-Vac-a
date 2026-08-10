# AUDITORÍA — REDIS DISTRIBUTION (Fase 11, post-corrección H2)

Fecha 2026-07-27. Estado tras corregir el self-echo detectado en la Auditoría Final de Fase 10.

## Defecto original (H2)

`RedisDistribution` publicaba y se suscribía al MISMO canal → la instancia origen recibía su propio evento por
Redis y lo entregaba **por segunda vez** a sus clientes (además de la entrega local original).

## Corrección implementada 🟢

- `INSTANCE_ID` único por proceso (configurable con env `INSTANCE_ID`; ECS lo inyecta por tarea).
- `sellar(ev, instance_id)` añade `_source_instance_id` a una COPIA (no muta el evento de dominio).
- `es_eco(ev, instance_id)` detecta el eco propio; `RedisDistribution._entregar_si_remoto` **descarta** el eco
  y `limpiar_sello` retira el metadato antes de repartir al hub (`realtime._on_event(_remoto=True)`).
- `InProcessBroker` (determinista, sin red) modela N instancias para probar la semántica exacta.

## Verificación

| Propiedad | Estado | Evidencia |
|---|---|---|
| Sin self-echo | 🟢 | `test_h2_broker_...`: origen A recibe 0 |
| Exactamente 1 entrega por instancia remota | 🟢 | B y C reciben 1 cada una |
| Sin duplicados | 🟢 | idem |
| Anti-loop (remoto no se reenvía) | 🟢 | `_on_event(_remoto=True)` no propaga (Fase 10) |
| Aislamiento por tenant | 🟢 | `id_empresa` intacto; hub filtra por tenant |
| Sello de transporte limpiado | 🟢 | `_source_instance_id` no llega al cliente |
| No rompe Local/InProcess | 🟢 | comportamiento local sin cambios |

## Límites honestos (🔵 / 🟡, requieren Redis real)

- **Reconexión**: `iniciar` no implementa reconexión con backoff ante caída de Redis → 🟡 (a completar antes de
  producción; documentado).
- **Semántica de entrega**: Redis Pub/Sub es at-most-once y sin orden garantizado entre instancias → para
  eventos que exijan garantía fuerte, usar un stream/cola persistente. Los eventos de UI (SSE) toleran esta
  semántica (el cliente resincroniza al reconectar).
- **Validación con Redis real**: 🟣 externo (no hay servidor Redis en el entorno).

## Estado

Self-echo **corregido y verificado** (determinista). Reconexión/orden y validación con Redis real quedan 🟡/🟣
para la fase de despliegue.
