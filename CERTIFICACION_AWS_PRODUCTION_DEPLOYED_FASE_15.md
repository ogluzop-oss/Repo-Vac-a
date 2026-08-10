# CERTIFICACIÓN — AWS PRODUCTION DEPLOYED (Fase 15)

Fecha 2026-07-27. Commit `fe7ab9d` (rama `main`). Regresión pre-deploy: **669 passed, 1 skipped, 0 failed**.

## Nivel alcanzado (honesto)

| Estado | Valor | Motivo |
|---|---|---|
| 🟢 SOFTWARE AWS PRODUCTION-READY | **SÍ** | mantiene la certificación de Fase 13/14; 0 cambios de código |
| 🟢 AWS PRE-DEPLOY READY | **SÍ** | sin bloqueantes de software |
| 🔴 **AWS PRODUCTION-DEPLOYED** | **NO** | no existe infraestructura AWS; nada desplegado |
| 🔴 **AWS PRODUCTION-VALIDATED** | **NO** | no se ha validado ningún componente sobre AWS real |

## Por qué no se declara DEPLOYED/VALIDATED

La **Regla Absoluta de Detención** se activó en la auditoría 15.0: los recursos externos imprescindibles **no
están disponibles** en el entorno:

- ❌ AWS CLI no instalado · ❌ credenciales AWS (0 `AWS_*`) · ❌ cuenta AWS · ❌ Terraform CLI · ❌ Docker daemon.

Sin cuenta AWS, credenciales ni herramientas, **no es posible** provisionar (15.1), IAM (15.2), RDS (15.3),
S3 (15.4), desplegar (15.5), ni validar SSE/jobs/secrets/DNS/observabilidad/backups/RPO-RTO/DR/E2E/carga/
multi-tenant/CI-CD/cutover (15.6–15.18). **No se simuló nada. No se inventaron credenciales/dominios/endpoints/
resultados. No se modificó el software para ocultar la ausencia de infra.**

## Criterios de éxito (Fase 15) — cumplimiento

Ninguno de los criterios de "🟢 AWS PRODUCTION DEPLOYED" (infra real, app desplegada, dominio, HTTPS, RDS, S3,
Redis, SQS, Secrets Manager, ECS, health checks) se cumple → **NO se declara DEPLOYED**. Los de "🟢 AWS
PRODUCTION VALIDATED" (multi-tenant/Storage/SSE/jobs/idempotencia/backups/RPO-RTO/DR/failover/rollback/
observabilidad validados en AWS) tampoco → **NO se declara VALIDATED**.

## Qué está validado / pendiente / bloqueado

- **Validado (software, local)**: storage CREATE/READ/DOWNLOAD/DELETE/LEGACY, multi-tenant, idempotencia
  atómica (BD), Redis sin self-echo (determinista), Docker hardened, secrets sin fallback inseguro,
  RDS-compatible, IaC HCL válido. 669 tests.
- **Pendiente (externo, propietario)**: instalar AWS CLI/Terraform/Docker; crear cuenta AWS + credenciales/OIDC;
  provisionar VPC/IAM/RDS/S3/KMS/Secrets/SQS/Redis/ECR/ECS/ALB/CloudFront/Route53/ACM/WAF/CloudWatch.
- **Bloqueado (🟣)**: todo despliegue y validación sobre AWS real (15.1–15.18).

## Variables necesarias (NOMBRES, nunca valores)

`AWS_REGION`, `AWS_ACCOUNT_ID`, `AWS_ROLE_ARN`, `DB_HOST/DB_PORT/DB_NAME/DB_USER`, `DB_PASSWORD`, `DB_SSL_CA`,
`SMART_MANAGER_JWT_SECRET`, `S3_BUCKET/S3_PREFIX/S3_SSE/S3_KMS_KEY_ID`, `SM_SECRET_BACKEND`, `SQS_QUEUE_URL/
SQS_DLQ_URL`, `JOB_QUEUE_BACKEND/JOB_IDEMPOTENCY_BACKEND`, `REALTIME_BROKER_URL`, `STORAGE_BACKEND`, `ECR_REPO/
ECS_CLUSTER/ECS_SERVICE/ALB_ARN`, `CDN_DOMAIN`, dominios `app./api./admin.`. **Valores sólo en Secrets Manager/
entorno; nunca en Git.**

## Punto de reanudación

**Fase 15.1 — Provisionado AWS real**, una vez instaladas las herramientas y provisionada la cuenta AWS. Ver
`AUDITORIA_PROVISIONADO_AWS_FASE_15.md` y `BLOQUEOS_EXTERNOS_AWS_FASE_9.md`.

## Veredicto final

**🟢 SOFTWARE AWS PRODUCTION-READY · 🔴 AWS PRODUCTION-DEPLOYED: NO · 🔴 AWS PRODUCTION-VALIDATED: NO · 🟣 TODA
LA INFRAESTRUCTURA AWS: BLOQUEADA POR RECURSO EXTERNO.** La Fase 15 se detiene en 15.0 conforme a la regla de
honestidad. No se inicia la Fase 16.
