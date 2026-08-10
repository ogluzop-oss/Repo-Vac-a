# AUDITORÍA DE PROVISIONADO AWS — FASE 15

Fecha 2026-07-27. **REGLA DE DETENCIÓN ACTIVADA.** El provisionado y despliegue reales en AWS **no pueden
comenzar**: los recursos externos imprescindibles NO están disponibles en este entorno. No se simula nada, no
se inventan credenciales/dominios/endpoints, no se declara ningún componente desplegado.

## 15.0 — Estado del entorno (verificado)

| Recurso requerido | Estado real | Comprobación |
|---|---|---|
| AWS CLI | ❌ NO instalado | `command -v aws` → not found |
| Credenciales AWS | ❌ NO existen | `aws sts get-caller-identity` → `aws: command not found`; `env AWS_*` → 0 variables |
| Cuenta/Organización AWS | ❌ NO disponible | sin CLI ni credenciales |
| Terraform CLI | ❌ NO instalado | `terraform -version` → not found |
| Docker daemon | ❌ NO disponible | `docker info` → error |
| Commit auditado | `fe7ab9d` (rama `main`) | `git rev-parse --short HEAD` |
| Regresión pre-deploy | 669 passed, 1 skipped, 0 failed | suite unit (código sin cambios desde Fase 14) |

## Consecuencia (honesta)

Ninguna de las operaciones de la Fase 15 (15.1–15.18) puede ejecutarse: no hay dónde provisionar, con qué
autenticarse, ni herramientas para construir/aplicar. **Detención inmediata** tras la auditoría 15.0.

- 🔴 **AWS PRODUCTION-DEPLOYED: NO** (nada desplegado).
- 🟣 **AWS PRODUCTION-VALIDATED: BLOQUEADO** (nada validado sobre AWS real).
- 🟢 **SOFTWARE AWS PRODUCTION-READY / AWS PRE-DEPLOY READY: SÍ** (mantiene el estado certificado en Fase 14;
  0 cambios de código).

## Qué debe provisionar el propietario (para reanudar)

Ver `BLOQUEOS_EXTERNOS_AWS_FASE_9.md` (B1–B10) + `INVENTARIO_AWS_REAL_FASE_15.md`. Requisitos mínimos para
reanudar la Fase 15:

1. **Herramientas locales**: instalar **AWS CLI**, **Terraform CLI** y disponer de **Docker daemon**.
2. **Cuenta AWS** (DEV/STAGING/PROD) + **credenciales/rol** (idealmente OIDC para CI; nunca claves en Git).
3. **Región(es)** objetivo.

### Variables necesarias (NOMBRES, nunca valores)

`AWS_REGION`, `AWS_ACCOUNT_ID`, `AWS_ROLE_ARN` (OIDC CI), `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD` (Secrets Manager), `DB_SSL_CA`, `SMART_MANAGER_JWT_SECRET`, `S3_BUCKET`, `S3_PREFIX`, `S3_SSE`,
`S3_KMS_KEY_ID`, `SM_SECRET_BACKEND=aws_secrets_manager`, `JOB_QUEUE_BACKEND=sqs`, `SQS_QUEUE_URL`,
`SQS_DLQ_URL`, `SQS_VISIBILITY_TIMEOUT`, `SQS_MAX_RECEIVE_COUNT`, `JOB_IDEMPOTENCY_BACKEND=db`,
`REALTIME_BROKER_URL`, `STORAGE_BACKEND=s3`, `ECR_REPO`, `ECS_CLUSTER`, `ECS_SERVICE`, `ALB_ARN`,
`CDN_DOMAIN`, dominios `app./api./admin.`. **Sus VALORES nunca en Git; sólo en Secrets Manager / entorno.**

## Punto exacto de reanudación

Reanudar en **Fase 15.1 — Provisionado AWS real** una vez instaladas las herramientas y provisionada la cuenta
AWS con credenciales. Secuencia: `terraform init/fmt/validate/plan` → revisión del plan → `apply` (con las
salvaguardas del prompt) → 15.2 (IAM) → 15.3 (RDS) → … → 15.19 (certificación).

## Cumplimiento de reglas

- ✅ No se simuló infraestructura, no se crearon mocks de producción, no se inventaron credenciales/dominios/
  endpoints/resultados.
- ✅ No se modificó el software para ocultar la ausencia de infra (0 cambios de código).
- ✅ No se declara DEPLOYED/VALIDATED.
