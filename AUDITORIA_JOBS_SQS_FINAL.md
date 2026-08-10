# AUDITORÍA JOBS / SQS FINAL (Fase 13)

Fecha 2026-07-27. Verificación final de jobs, idempotencia y worker IA. Read-only. Amplía
`AUDITORIA_JOBS_IDEMPOTENCY.md` y `AUDITORIA_IDEMPOTENCIA_MULTIWORKER.md`.

## Componentes (verificados)

- `Job` (con `id_empresa` obligatorio, `attempt`, `correlation_id`), `LocalQueue`, `SQSQueue`, `worker`.
- Idempotencia: backend `memory` (DEV/single) / `db` (multi-worker, migr 0165 `jobs_idempotencia`).
- `reclamar()` atómico; clasificación `JobErrorPermanente`/`JobErrorTemporal`; DLQ/retries.

## Propiedades verificadas (tests)

| Propiedad | Estado | Evidencia |
|---|---|---|
| `id_empresa` obligatorio | 🟢 | `Job('')` → ValueError |
| Dos workers, mismo job → sólo uno ejecuta | 🟢 | `test_h3_reclamo_atomico_db`: claimed / en_curso |
| Job completado → reentrega ignorada | 🟢 | `duplicate` tras COMPLETADO |
| Error permanente → FAILED (DLQ) | 🟢 | `test_h3_error_permanente_no_reintenta` |
| Error temporal → retry acotado → DLQ | 🟢 | `test_h3_error_temporal_agota_a_dlq` |
| Tipo no soportado → permanente | 🟢 | `test_h3_tipo_no_soportado_es_permanente` |
| Backend memory (DEV) | 🟢 | `test_h3_reclamo_memoria` |
| Worker = motor único (sin 2º forecasting/retraining) | 🟢 | invoca `forecasting`/`retraining`/`modelos` |
| Tenant aislado en ejecución | 🟢 | worker ejecuta en `job.id_empresa` |
| SQS delete-tras-éxito + visibility + DLQ config | 🟢 | `SQSQueue.confirmar/rechazar`, `SQS_*` env |

## Atomicidad multi-worker

`INSERT` con PK `job_id` (IntegrityError en todos menos uno) + `UPDATE ... WHERE estado IN ('PENDIENTE',
'FALLIDO')` (atómico por fila InnoDB). Sin locks aplicativos ni polling. Producción **debe** usar
`JOB_IDEMPOTENCY_BACKEND=db` (ya en `.env.production.example`); `memory` sólo DEV/tests.

## Límites honestos

- **SQS no está disponible** (sin boto3/cola) → `SQSQueue` es 🔵 preparado / 🟣 no operativo. La idempotencia se
  prueba contra **MariaDB local**; la validación multi-worker con **SQS real distribuido** es 🟣 externa.

## Veredicto

🟢 **Jobs idempotentes y robustos** (dedup atómico multi-worker, DLQ/retries, tenant aislado, motor único).
Validación con SQS real 🟣 externa.
