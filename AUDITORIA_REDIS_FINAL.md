# AUDITORÍA REDIS FINAL (Fase 13)

Fecha 2026-07-27. Verificación final de la distribución de eventos multi-instancia. Read-only. Amplía
`AUDITORIA_REDIS_DISTRIBUTION.md`.

## Componentes (verificados)

- `INSTANCE_ID` único por proceso (env `INSTANCE_ID` o autogenerado).
- `sellar(ev, id)` / `es_eco(ev, id)` / `limpiar_sello(ev)` — helpers puros, testeables sin Redis.
- `RedisDistribution` (boto3/`redis` perezoso) — `publicar` sella origen; `_entregar_si_remoto` descarta eco.
- `InProcessBroker` — modelo determinista multi-instancia (sin red) para tests.
- Cableado en `realtime._on_event(ev, _remoto=)`: eventos locales se propagan; remotos NO se reenvían (anti-loop).

## Propiedades verificadas (tests)

| Propiedad | Estado | Evidencia |
|---|---|---|
| A publica → A recibe 0 ecos | 🟢 | `test_h2_broker_...` (origen A: 0) |
| B/C reciben exactamente 1 | 🟢 | idem |
| Sin duplicados | 🟢 | idem |
| Sin loops (A→Redis→A→…) | 🟢 | `_remoto=True` no propaga |
| Tenant intacto A↛B | 🟢 | `id_empresa` en el evento; hub filtra |
| Sello de transporte limpiado | 🟢 | `_source_instance_id` no llega al cliente |
| No rompe Local/InProcess/DEV | 🟢 | comportamiento local sin cambios |

## Límites honestos

- **Redis no está instalado ni hay servidor** → `RedisDistribution` es 🔵 preparado / 🟣 no operativo. La lógica
  de anti-self-echo y aislamiento se prueba de forma determinista (`InProcessBroker`), NO contra Redis real.
- **Reconexión/backoff** ante caída de Redis: 🟡 pendiente de completar antes de producción (documentado).
- Semántica Pub/Sub at-most-once/sin orden: aceptable para eventos de UI (el cliente resincroniza).

## Veredicto

🟢 **Self-echo corregido y verificado** (determinista); aislamiento por tenant intacto. Validación con Redis
real (ElastiCache) 🟣 externa. Reconexión 🟡 (mejora previa a producción, no bloqueante del software actual).
