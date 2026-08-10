# RUNBOOK — Rollback y Actualización (AWS)

## Actualización de la aplicación (deploy de nueva versión)

1. Merge a `main` → pipeline `aws-deploy.yml` (manual, por entorno, con approval del *environment*).
2. Build imagen con `TAG = SHA` (inmutable) → push a ECR.
3. Registrar **nueva task definition** (misma familia, nueva imagen) y `aws ecs update-service
   --force-new-deployment`.
4. ECS hace **rolling update** (`minimum_healthy_percent=100`, `maximum_percent=200`) → sin downtime.
5. Smoke: `/api/v1/health/ready`. Si falla, el despliegue no estabiliza → rollback.

## Rollback de aplicación (a la versión anterior)

- Cada despliegue crea una revisión de task definition. Para revertir:
  ```bash
  aws ecs update-service --cluster <cluster> --service <service> \
    --task-definition <familia>:<REVISION_ANTERIOR>
  ```
- ECS reprograma con la revisión previa (imagen anterior, ya en ECR). Verificar `/api/v1/health/ready`.
- Mantener al menos las **N** últimas revisiones/imágenes para poder revertir.

## Rollback de infraestructura (Terraform)

- Un cambio de IaC problemático se revierte con `git revert` del commit de infra + `terraform apply` del estado
  anterior, **revisando el `plan`**. Nunca `terraform destroy` de recursos con datos (RDS/S3) sin backup.
- Cambios destructivos (RDS/S3) están protegidos: `deletion_protection=true` (RDS), Block Public Access +
  versioning (S3).

## Migraciones de BD y compatibilidad

- Las migraciones son **idempotentes y aditivas** (ADD COLUMN/CREATE TABLE IF NOT EXISTS). Una versión nueva
  aplica migraciones pendientes al arrancar. Para rollback de app sin rollback de esquema: las columnas nuevas
  son opcionales (backward-compatible), por lo que la versión anterior sigue funcionando.
- Si una migración es incompatible hacia atrás (evitarlo), coordinar con snapshot RDS previo.

## Ventana y verificación

- Preferir horario de bajo tráfico. Tras rollback/actualización: revisar CloudWatch (5xx, latencia, CPU) y
  alarmas durante 15–30 min.
