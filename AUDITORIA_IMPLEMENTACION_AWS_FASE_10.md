# AUDITORÍA DE IMPLEMENTACIÓN — AWS Production Readiness (Fase 10)

Fecha 2026-07-27. Resumen de lo IMPLEMENTADO en esta fase (software AWS-ready, sin desplegar AWS). Todo
aditivo, N7, degradable, multi-tenant, 0 regresiones.

## Ficheros nuevos

| Fichero | Responsabilidad |
|---|---|
| `src/services/storage/base.py` | `StorageProvider` + guard de tenant + URLs firmadas con autorización |
| `src/services/storage/local.py` | Backend local (DEV, filesystem seguro) |
| `src/services/storage/s3.py` | Backend S3 (boto3 perezoso, SSE-KMS, presigned) — PREPARADO/degradable |
| `src/services/storage/__init__.py` | Factory `obtener_storage()` por `STORAGE_BACKEND` (sin fallback silencioso) |
| `src/services/storage/migracion.py` | Migración local→S3 no destructiva (checksum, sin borrar) |
| `src/services/eventbus/distribucion.py` | LocalDistribution + InProcessDistribution (tests) + RedisDistribution (degradable) |
| `src/services/jobs/base.py` | `Job` (tenant obligatorio) + `JobQueue` |
| `src/services/jobs/local.py` | `LocalQueue` (DEV) |
| `src/services/jobs/sqs.py` | `SQSQueue` (boto3 perezoso) — PREPARADO/degradable |
| `src/services/jobs/worker.py` | Worker IA: reutiliza forecasting/retraining/degradación; audita; emite SSE |
| `src/services/jobs/__init__.py` | Factory `obtener_cola()` + `encolar_prediccion/retrain` |
| `gunicorn.conf.py` | Worker `gevent` (SSE) + keepalive/timeout para ALB |
| `infra/aws/main.tf` | IaC skeleton (NO aplicado) |
| `tests/unit/test_aws_readiness_fase10.py` | 14 tests (aislamiento storage/eventos/jobs, degradables AWS) |

## Ficheros modificados (aditivo, sin romper comportamiento por defecto)

| Fichero | Cambio |
|---|---|
| `src/services/eventbus/realtime.py` | `_on_event(..., _remoto=)` propaga eventos locales al adaptador de distribución (no reenvía remotos → sin bucles); single-instance por defecto sin cambios |
| `src/services/seguridad/secret_manager.py` | Backend `aws_secrets_manager` (boto3 perezoso, cache TTL, sin fallback inseguro en prod) + `disponible_aws`/`backend_activo` |
| `Dockerfile` | Usuario non-root (uid 10001), TMPDIR, HEALTHCHECK, `gevent`, `gunicorn -c gunicorn.conf.py` |
| `.env.production.example` | Variables AWS (nombres/config, sin secretos): STORAGE_BACKEND/S3_*/SM_SECRET_BACKEND/JOB_QUEUE_BACKEND/SQS_QUEUE_URL/REALTIME_BROKER_URL/AWS_REGION |

## Reutilización (N7) — 0 sistemas paralelos

- Storage: los módulos de negocio migrarán a `obtener_storage()`; la generación de PDFs NO cambia (sólo dónde
  se persiste/lee el binario).
- Eventos: la distribución es TRANSPORTE; el Event Bus de dominio y el hub SSE siguen siendo la única lógica.
- Jobs/IA: el worker INVOCA `forecasting`/`retraining` existentes; no hay segundo motor de predicción.
- Secretos: misma interfaz `obtener_secreto`; sólo cambia el backend.

## Pendiente honesto

- Migrar los puntos de escritura de `documentos/` a `obtener_storage()` (gradual, compatible) — servicio listo.
- Backends AWS reales requieren boto3 + infraestructura (🔵 hasta provisionar).
