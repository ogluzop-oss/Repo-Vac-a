# AUDITORÍA — IDEMPOTENCIA DE JOBS (Fase 11, post-corrección H3)

Fecha 2026-07-27. Estado tras corregir la falta de idempotencia detectada en la Auditoría Final de Fase 10.

## Defecto original (H3)

SQS es at-least-once; el worker no deduplicaba → reproceso de un job podía duplicar forecast/modelos/eventos.

## Corrección implementada 🟢

| Requisito | Implementación |
|---|---|
| Identidad de job | `Job` con `id`, `id_empresa`, `tipo`, `payload`, `created_at`, `attempt`, `estado`, `correlation_id` |
| Guard de idempotencia | `services/jobs/idempotencia` (backend `memory`/`db`): si `ya_completado(job.id)` → NO ejecuta |
| Duplicado auditado | evento `JOB_DUPLICATE_IGNORED` |
| Resultado idempotente | el guard a nivel de job evita el doble efecto (forecast/retraining/modelos no se repiten) |
| Clasificación de errores | `JobErrorPermanente` (FAILED/DLQ, sin reintento) vs `JobErrorTemporal` (reintento controlado) |
| Retries | hasta `JOB_MAX_ATTEMPTS`/`SQS_MAX_RECEIVE_COUNT`; luego DLQ. Sin reintentos infinitos |
| SQS delete tras éxito | `SQSQueue.confirmar` borra sólo al completar; `rechazar` deja reentregar; `VisibilityTimeout` configurable |
| DLQ | `SQS_DLQ_URL` (config, sin infra); al agotar intentos → estado FALLIDO/DLQ |
| Auditoría | `JOB_CREADO/INICIADO/RETRIED/COMPLETADO/FAILED/DUPLICATE_IGNORED` (con tenant y usuario) |
| Tenant | `id_empresa` obligatorio; worker ejecuta sólo en ese tenant |

## Verificación (tests)

| Caso | Estado |
|---|---|
| Job repetido (mismo `job_id`) no se re-ejecuta (`duplicado`) | 🟢 `test_h3_idempotencia_no_reejecuta` |
| Error permanente → FAILED, sin reintento | 🟢 `test_h3_error_permanente_no_reintenta` |
| Error temporal agota intentos → DLQ | 🟢 `test_h3_error_temporal_agota_a_dlq` |
| Tipo no soportado → permanente | 🟢 `test_h3_tipo_no_soportado_es_permanente` |
| `id_empresa` obligatorio | 🟢 (Fase 10) |
| Worker = motor único (sin 2º forecasting/retraining) | 🟢 (reutiliza servicios) |

## Nota de honestidad

- El backend de idempotencia por defecto es `memory` (válido para LocalQueue/DEV y **un** worker). Para
  **multi-worker SQS real** se requiere el backend `db` (tabla `jobs_idempotencia`) o DynamoDB; el código lo
  soporta y degrada a memoria si la tabla no existe (sin corromper: en el peor caso, sin dedup entre procesos,
  = comportamiento previo). La tabla persistente y su migración se crean en la fase de despliegue (🔵).
- Validación con SQS real: 🟣 externo (sin cola AWS en el entorno).

## Estado

Idempotencia/retries/DLQ **implementados y verificados** a nivel de worker/cola. Dedup entre workers en
producción requiere el backend `db`/DynamoDB (🔵) + SQS real (🟣).
