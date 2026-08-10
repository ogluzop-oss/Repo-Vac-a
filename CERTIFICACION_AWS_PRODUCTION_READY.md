# CERTIFICACIÓN — AWS PRODUCTION-READY SOFTWARE (Fase 10)

Fecha 2026-07-27. Adaptación del software a arquitectura AWS **sin desplegar** AWS. Reglas: N7 (sin sistemas
paralelos), backends AWS **degradables** (boto3/redis perezosos; sin AWS → PREPARADO, nunca operativo), 0
simulación de infraestructura, multi-tenant estricto, 0 regresiones.

## Los tres estados (no confundir)

| Estado | Veredicto |
|---|---|
| **SOFTWARE PRODUCTION-READY** | 🟢 SÍ |
| **AWS PRODUCTION-READY SOFTWARE** | 🟢 SÍ (adaptaciones de software implementadas y verificadas localmente) |
| **AWS PRODUCTION-DEPLOYED** | 🔴 NO (sin infraestructura AWS provisionada) |

## Matriz final (Fase 25)

Estados: 🟢 implementado y verificado (local) · 🔵 preparado (activa con AWS) · 🟡 parcial · 🟣 externo · 🔴 no.

| Componente | Estado | Evidencia |
|---|---|---|
| Docker non-root | 🟢 | Dockerfile `USER appuser` (uid 10001), TMPDIR propio, HEALTHCHECK |
| Storage abstraction | 🟢 | `services/storage` (StorageProvider + factory); tests aislamiento |
| S3 adapter | 🔵 | `storage/s3.py` boto3 perezoso; degradable verificado |
| S3 tenant isolation | 🟢 | guard en clase base (`tenant/{id_empresa}/…`); tests A≠B, path traversal, id manipulation |
| Signed URLs | 🟢 | `url_firmada` exige tenant + `autorizado`; test |
| Secrets Manager adapter | 🔵 | `secret_manager` backend `aws_secrets_manager` (boto3 perezoso, sin fallback inseguro en prod) |
| KMS readiness | 🔵 | `S3_SSE=aws:kms` + `S3_KMS_KEY_ID` en S3; config lista |
| RDS MariaDB readiness | 🟢 (software) | `db/conexion.py` SSL/pool/utf8mb4; esquema InnoDB sin SUPER |
| SSE AWS readiness | 🟢 | `gunicorn.conf.py` worker `gevent`; keepalive>idle ALB; heartbeat 15s |
| Multi-instance events | 🟢 (lógica) / 🔵 (broker) | `realtime._on_event` propaga a distribución; test forward/no-loop/aislamiento |
| Broker adapter | 🔵 | `eventbus/distribucion.py` Redis perezoso; InProcess determinista para tests |
| Job Queue | 🟢 | `services/jobs` (JobQueue + LocalQueue + factory); tests |
| SQS adapter | 🔵 | `jobs/sqs.py` boto3 perezoso; degradable verificado |
| AI Worker | 🟢 | `jobs/worker.py` reutiliza forecasting/retraining; test procesa forecast tenant-aislado |
| Prophet async | 🟢 (patrón) | forecast como job fuera del request; worker separable en ECS |
| Tenant isolation jobs | 🟢 | `Job` exige `id_empresa`; worker ejecuta sólo en ese tenant; tests |
| Observability | 🟢 (hook) / 🔵 (CloudWatch) | métricas de storage/jobs vía observabilidad existente; logs JSON → awslogs |
| CI | 🟢 | pipeline real (lint/i18n/tests); gates reutilizables |
| CD readiness | 🔵 | plantillas OIDC→ECR→ECS documentadas (`AUDITORIA_CI_CD_AWS`) |
| IaC | 🔵 | `infra/aws/main.tf` esqueleto (NO aplicado) |
| Backups | 🔵 | `dr/*` reutilizable; mapeo RDS snapshots + S3 versioning |
| DR | 🟡 / 🟣 | Multi-AZ/cross-region + simulacro real → externo |

## Regresión (Fase 23)

Baseline 638 → **652 passed, 1 skipped, 0 failed**. Se añaden 14 tests de Fase 10 (aislamiento storage/eventos/
jobs, degradables AWS). **0 regresiones** (los cambios son aditivos; el comportamiento por defecto local no
cambia).

## Honestidad (Fase 27)

No se afirma que S3/SQS/Redis/RDS/ECS/CloudFront estén operativos: **no existen recursos reales**. Los
adaptadores son 🔵 PREPARADOS y degradan de forma explícita (error claro, sin fallback inseguro, sin mocks
presentados como producción). El despliegue real es una fase posterior con AWS provisionado.

**Veredicto: AWS PRODUCTION-READY SOFTWARE 🟢 · AWS PRODUCTION-DEPLOYED 🔴.**
