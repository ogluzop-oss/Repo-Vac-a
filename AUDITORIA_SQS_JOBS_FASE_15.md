# AUDITORÍA SQS / JOBS — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay SQS ni boto3.**

## Software (verificado)

🟢 `Job` (id_empresa obligatorio), `SQSQueue` (confirmar/rechazar+VisibilityTimeout+DLQ config), worker con
idempotencia atómica multi-worker (`idempotencia.reclamar`, tabla `jobs_idempotencia` migr 0165),
clasificación permanente/temporal, retries≤`JOB_MAX_ATTEMPTS`→DLQ, `JOB_DUPLICATE_IGNORED`. Worker IA reutiliza
`forecasting`/`retraining` (motor único, sin duplicar). Producción usa `JOB_IDEMPOTENCY_BACKEND=db`.

## Validación en AWS (Fase 15.7)

🟣 **BLOQUEADA**. No ejecutado sobre SQS real: Worker 1 reclama / Worker 2 → `JOB_DUPLICATE_IGNORED`; éxito;
retry temporal; fallo permanente→DLQ; VisibilityTimeout; forecasting/Prophet/retraining reales; aislamiento
por tenant. (La idempotencia atómica SÍ está probada contra MariaDB local.)

## Resume

Provisionar cola SQS + DLQ; instalar boto3. Variables: `SQS_QUEUE_URL`, `SQS_DLQ_URL`, `SQS_VISIBILITY_TIMEOUT`,
`SQS_MAX_RECEIVE_COUNT`, `JOB_QUEUE_BACKEND=sqs`, `JOB_IDEMPOTENCY_BACKEND=db`. Validar dedup multi-worker sobre
SQS real. Estado: 🟢 software (dedup probado en BD) / 🟣 validación SQS externa.
