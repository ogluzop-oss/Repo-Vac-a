# RUNBOOK — Despliegue AWS (Smart Manager AI)

> Estado actual: **NADA desplegado**. Este runbook describe el procedimiento para el día del despliegue real.
> Requisitos: AWS CLI + Terraform instalados, cuenta AWS + credenciales/rol, `infra/aws` (IaC preparada).

## 0. Preparación (una vez)

1. Crear bucket S3 + tabla DynamoDB para el **estado remoto de Terraform** (fuera del stack).
2. Copiar `environments/<env>.s3.tfbackend.example` → `<env>.s3.tfbackend` (rellenar bucket/region/tabla).
3. Copiar `environments/<env>.tfvars.example` → `<env>.tfvars`.
4. `terraform fmt -recursive` (formato canónico).

## 1. Provisionado por capas (activar `enable_*` gradualmente en el tfvars)

Orden: `iam_oidc → secrets → network → s3 → rds → observability → ecs`.

```bash
cd infra/aws
terraform init -backend-config=environments/<env>.s3.tfbackend
terraform validate
# Activar network primero (enable_network=true en <env>.tfvars), revisar y aplicar:
terraform plan  -var-file=environments/<env>.tfvars
terraform apply -var-file=environments/<env>.tfvars   # revisar SIEMPRE el plan antes
```

Repetir activando cada `enable_*` en el orden indicado, revisando el `plan` en cada paso.

## 2. Secretos (tras `enable_secrets`)

- Rellenar los VALORES de los secretos creados (`<project>-<env>/SMART_MANAGER_JWT_SECRET`, `.../correo_key`,
  `.../GOOGLE_OAUTH_CLIENT_SECRET`) por consola/CLI (NUNCA en Git).
- Config app: `SM_SECRET_BACKEND=aws_secrets_manager`, `SM_SECRET_PREFIX=<project>-<env>/`.

## 3. Base de datos (tras `enable_rds`)

- Config app: `DB_HOST`=endpoint RDS, `DB_SSL_CA`=bundle `rds-combined-ca` (RDS fuerza TLS).
- Aplicar migraciones: arrancar un contenedor/one-off con la imagen y ejecutar el arranque (migraciones
  auto-aplican) o `python -c "from src.db.conexion import ensure_schema; ensure_schema()"`.
- Smoke: `/api/v1/health/ready` (200 si la BD responde).

## 4. Imagen + ECS (tras `enable_ecs`)

- Build & push a ECR con tag = SHA (ver `.github/workflows/aws-deploy.yml.disabled`).
- La task definition inyecta secretos por `valueFrom` (Secrets Manager) y `DB_PASSWORD` desde el secret
  gestionado de RDS. Logs → CloudWatch (`awslogs`).
- `certificate_arn` (ACM) habilita el listener HTTPS; sin él, sólo HTTP (fase de dominio posterior).
- Autoscaling por CPU (65%), min/max configurables.

## 5. Verificación post-despliegue

- ALB target `/api/v1/live` → 200; `/api/v1/health/ready` → 200.
- Login de prueba; crear/leer un documento (S3); publicar un evento (SSE) si aplica.
- CloudWatch: logs y métricas presentes; alarmas en estado OK.

## 6. Config de la app en ECS (variables de entorno)

`AWS_ENABLED=true`, `STORAGE_BACKEND=s3` (+ `S3_BUCKET/S3_SSE/S3_KMS_KEY_ID`), `SM_SECRET_BACKEND=aws_secrets_manager`
(+ `SM_SECRET_PREFIX`), `JOB_IDEMPOTENCY_BACKEND=db`, `GUNICORN_WORKER_CLASS=gevent`. Secretos por Secrets
Manager (nunca en `environment`).

> No enviar tráfico público hasta que el health-check del target group esté en estado *healthy*.
