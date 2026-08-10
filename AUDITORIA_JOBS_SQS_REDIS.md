# AUDITORÍA — JOBS (SQS) y DISTRIBUCIÓN (Redis) (Fase 10)

Fecha 2026-07-27. Auditoría read-only de `services/jobs/*` y `services/eventbus/distribucion.py`. Ambos
backends AWS son 🔵 PREPARADOS (boto3/redis no instalados; degradables). Se detectan **defectos reales que
deben corregirse ANTES de activarlos** en AWS (no se corrigen aquí — regla de detención).

## A · Distribución de eventos (Redis)

| Aspecto | Estado | Observación |
|---|---|---|
| Local / InProcess | 🟢 | probados; aislamiento por tenant OK |
| Anti-loop (evento remoto no se reenvía) | 🟢 | `_on_event(_remoto=True)` no propaga |
| Aislamiento por tenant | 🟢 | `id_empresa` viaja en el evento; hub filtra |
| **Self-echo / doble entrega** | 🔴 **DEFECTO (HIGH, en path 🔵)** | `RedisDistribution.publicar` publica en `_canal` y `iniciar` se **suscribe al mismo canal**. Redis Pub/Sub entrega a TODOS los suscriptores **incluido el publicador** → la instancia origen entrega el evento **dos veces** a sus clientes (una por el `_on_event` local original y otra por el eco de Redis). Falta un filtro por `instance_id`/source. |
| Reconexión / pérdida de eventos | 🟡 | `iniciar` no maneja reconexión ante caída de Redis; Pub/Sub no persiste (eventos perdidos si un suscriptor está caído) |
| Orden de eventos | 🟡 | Pub/Sub no garantiza orden entre instancias |

**Recomendación (antes de activar Redis)**: añadir `instance_id` al mensaje y descartar en `_entregar` los
mensajes cuyo `instance_id` sea el propio; manejar reconexión con backoff; documentar la semántica at-most-once
de Pub/Sub (para eventos que exijan garantía, usar un stream/cola persistente).

## B · Jobs (SQS) y worker

| Aspecto | Estado | Observación |
|---|---|---|
| `id_empresa` obligatorio | 🟢 | `Job` lanza ValueError sin tenant; verificado |
| Aislamiento por tenant | 🟢 | worker ejecuta el forecast en el tenant del job; MessageAttribute id_empresa |
| Serialización | 🟢 | `to_dict`/`from_dict` (JSON) |
| Reutiliza motores existentes | 🟢 | `worker` invoca `forecasting`/`retraining`/`modelos` (sin segundo motor) |
| Auditoría | 🟢 | `JOB_CREADO/INICIADO/COMPLETADO/FALLIDO` |
| **Idempotencia / dedup** | 🟡 **(MEDIUM, en path 🔵)** | SQS es **at-least-once**; el worker no deduplica. Reproceso → `forecasting.predecir_ventas` persiste un modelo por ejecución → posibles **modelos duplicados**. |
| DLQ / poison messages | 🟡 | no hay manejo de DLQ ni contador de reintentos en el código (se delega a la config SQS, aún inexistente) |
| Worker muere a mitad | 🟡 | sin idempotencia, la reentrega de SQS reprocesa (efecto: modelo duplicado; no corrupción de stock) |
| SSE no disponible al emitir | 🟢 | `_emitir` va por Event Bus (degradable); el resultado se persiste igualmente |

**Recomendación (antes de activar SQS)**: clave de idempotencia por `correlation_id`/`job.id` (marca de
"ya procesado"), y política DLQ + visibility timeout ≥ duración de Prophet; hacer que la persistencia del
modelo sea idempotente por `correlation_id`.

## C · Worker IA — motor único (🟢)

Verificado: el worker NO contiene un segundo motor. Llama a `forecasting.predecir_ventas`,
`retraining.retrain`, `modelos.evaluar_degradacion`. Prophet/heurística/estadística/backtesting/persistencia/
degradación siguen en el motor único.

## Resumen

- Jobs/distribución **local**: 🟢 (probados, aislados).
- Backends **AWS (SQS/Redis)**: 🔵 PREPARADOS con **2 defectos a corregir antes de activar**: self-echo Redis
  (HIGH) e idempotencia de jobs (MEDIUM). No afectan a la operación actual (backends inactivos), pero impiden
  declarar esos caminos "listos para producción" sin corrección.
