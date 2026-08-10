# PLAN DE MIGRACIÓN AWS — Smart Manager AI (conceptual, Fase 9)

Plan por fases. **No se ejecuta ninguna aquí.** Para cada fase: qué hace Claude Code (código/IaC), qué hace el
propietario (provisión/credenciales), recursos externos y variables necesarias.

| Fase | Qué hace Claude Code | Qué hace el propietario | Recursos AWS | Variables/inputs |
|---|---|---|---|---|
| **A · Configuración** | Clasificar variables, plantillas de config por entorno, backend `aws`/`vault` en `secret_manager` | Aprobar clasificación | — | (ninguna secreta) |
| **B · Docker** | `USER` no-root, worker gunicorn async (gevent), `.dockerignore`, capa `storage` (fs/s3), pin health path | — | — | — |
| **C · Preparar AWS** | IaC (Terraform/CDK) de VPC/ECS/RDS/S3/Secrets/ECR (plantillas) | Crear cuenta, activar regiones, budgets/alertas de coste | Cuenta AWS, IAM admin inicial | `AWS_ACCOUNT_ID`, `AWS_REGION` |
| **D · Staging** | Task defs, ALB target group, pipeline OIDC→ECR→ECS staging | Provisionar VPC/subnets/SG, ECR, cluster ECS staging | VPC, ECS, ECR, ALB | subnets/SG IDs, ECR repo |
| **E · Migrar MariaDB** | Script de migración/seed vía `migraciones`, activar TLS RDS, parameter group | Crear RDS MariaDB (Multi-AZ), CA bundle, credenciales | RDS MariaDB | `DB_HOST/PORT/NAME/USER`, `DB_SSL_CA`, `DB_PASSWORD` (Secrets) |
| **F · Migrar S3** | Backend S3 en capa `storage`, URLs firmadas, migración de ficheros `documentos/`→S3 | Crear bucket privado + KMS + CloudFront OAC | S3, KMS, CloudFront | `S3_BUCKET`, `KMS_KEY_ID`, `CDN_DOMAIN` |
| **G · Secrets Manager** | Implementar backend AWS en `secret_manager`, mover JWT/DB/OAuth/`.correo_key` | Crear secretos + política de rotación | Secrets Manager, KMS | ARNs de secretos |
| **H · Desplegar ECS** | Servicios `api` + `worker-ia`, autoscaling, secrets en task def | Aprobar despliegue | ECS Fargate, ALB | task CPU/mem, desired count |
| **I · DNS/TLS** | Config CloudFront/ALB, cabeceras SSE, WAF rules | Registrar dominio, zona Route 53, ACM cert | Route 53, ACM, CloudFront, WAF | `app./api./admin.` dominios |
| **J · Pruebas** | Smoke + E2E + prueba SSE detrás de CloudFront + aislamiento tenant | Validar | — | — |
| **K · Producción** | Deploy PROD con approval, tag release, runbook rollback | Aprobar go-live | (cuenta/VPC PROD) | — |
| **L · DR** | Scripts de restore/simulacro sobre RDS snapshots + S3 cross-region | Activar Multi-AZ + cross-region + retención | RDS Multi-AZ, S3 CRR | RPO/RTO objetivo |

## Orden crítico y dependencias

- **B** (Docker/storage) y **A** (config/secrets) son prerequisito de todo → **empezar por software**.
- **E/F/G** (RDS/S3/Secrets) antes de **H** (ECS) — el runtime necesita datos, ficheros y secretos.
- **I** (DNS/TLS) tras tener ALB/ECS estables en staging.
- **L** (DR) sólo tiene sentido con PROD provisionado; simulacro real = evidencia para certificar DR.

## Reglas permanentes durante la migración

Reutilizar (no reemplazar) MariaDB, multi-tenant, RBAC/MFA/WebAuthn/auditoría, Event Bus/SSE, predicción/SOMA,
Secret Manager, observabilidad. No crear motores/tablas/pipelines paralelos. No simular recursos.
