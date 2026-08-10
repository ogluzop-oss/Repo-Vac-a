# Smart Manager AI — Infraestructura como Código AWS (PREPARADA, NO desplegada)

Terraform modular que prepara AWS para Smart Manager **sin desplegar nada**. Base de datos: **MariaDB** (Amazon
RDS for MariaDB). Nada se crea por defecto: todos los `enable_*` están en `false`.

## ⚠️ Seguridad y coste

- **Nada se despliega** ejecutando esto tal cual: cada módulo se instancia con `count = var.enable_* ? 1 : 0`
  y todos los interruptores están en `false`. Un `terraform apply` por defecto crea **0 recursos**.
- **Sin secretos en el repositorio**: contraseñas/claves se gestionan en **AWS Secrets Manager** (el módulo
  `secrets` crea los *contenedores*, no los valores) y la de RDS con `manage_master_user_password`.
- **Estado remoto desactivado** (`backend.tf` comentado) → no puede aplicar contra AWS por accidente.

## Estructura

```
infra/aws/
  versions.tf · backend.tf · variables.tf · main.tf · outputs.tf
  terraform.tfvars.example
  environments/{dev,staging,production}.tfvars.example
  modules/
    network/         VPC, subnets públicas/privadas, NAT, SG de app
    rds/             RDS MariaDB (privado, KMS, TLS, backups, parameter group utf8mb4/UTC)
    s3/              bucket privado documentos (SSE-KMS, versioning, lifecycle, Block Public Access)
    secrets/         Secrets Manager + KMS (contenedores, sin valores)
    observability/   CloudWatch log groups + alarma base
    ecs/             ECR + ECS/Fargate + ALB (esqueleto)
    iam_oidc/        OIDC GitHub Actions + rol de despliegue (mínimo privilegio)
```

## Mapeo app → AWS

| App | AWS | Variable de entorno |
|---|---|---|
| `db/conexion.py` (MariaDB, SSL-ready) | RDS MariaDB | `DB_HOST/PORT/NAME/USER`, `DB_PASSWORD`(Secrets), `DB_SSL_CA` |
| `StorageProvider` (`storage/s3.py`) | S3 privado + KMS | `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_SSE`, `S3_KMS_KEY_ID` |
| `secret_manager` (backend `aws_secrets_manager`) | Secrets Manager + KMS | `SM_SECRET_BACKEND=aws_secrets_manager`, `SM_SECRET_PREFIX=<project>-<env>/` |
| `observabilidad` (logs JSON) | CloudWatch (`awslogs`) | — |
| jobs (`SQSQueue`) | SQS + DLQ (añadir módulo al activar) | `JOB_QUEUE_BACKEND=sqs`, `SQS_QUEUE_URL`, `SQS_DLQ_URL` |
| distribución SSE (`RedisDistribution`) | ElastiCache Redis (añadir módulo al activar) | `REALTIME_BROKER_URL` |
| backend gunicorn/gevent | ECS/Fargate + ALB | — |
| CI/CD | OIDC + ECR/ECS | `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION` |

## Comandos FUTUROS (NO ejecutar ahora)

Requieren: AWS CLI + Terraform instalados y una cuenta AWS con credenciales/rol. Se ejecutan por el propietario.

```bash
cd infra/aws
terraform fmt -recursive
terraform init                 # (configura antes backend.tf con el bucket/tabla de estado)
terraform validate
# Provisionado por capas (activando enable_* en el tfvars del entorno):
terraform plan  -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars   # ← el propietario decide; NO se ejecuta en esta fase
```

Orden recomendado de activación (editar `enable_*` en el tfvars): `network` → `secrets` → `s3` → `rds` →
`observability` → `ecs` → `ci_oidc`. Revisar SIEMPRE el `plan` antes de aplicar.

### Aislamiento de estado por entorno (B-1)

El estado remoto está DESACTIVADO (`backend.tf` comentado) hasta que exista el bucket. Cuando el propietario
cree el bucket/tabla de estado, se usa **configuración parcial de backend** con una **key por entorno** (ver
`environments/<env>.s3.tfbackend.example`), de modo que dev/staging/prod **nunca** comparten `tfstate`:

```bash
terraform init -backend-config=environments/dev.s3.tfbackend
terraform init -reconfigure -backend-config=environments/staging.s3.tfbackend
terraform init -reconfigure -backend-config=environments/prod.s3.tfbackend
```

### Secretos por entorno (A-1)

El módulo `secrets` nombra los secretos como `${project}-${environment}/<CLAVE>`. La app los resuelve con
`SM_SECRET_PREFIX=${project}-${environment}/` (p. ej. `smart-manager-production/`), así
`obtener_secreto("SMART_MANAGER_JWT_SECRET")` busca `smart-manager-production/SMART_MANAGER_JWT_SECRET`. Sin
prefijo, usa el nombre desnudo. **Nunca se guardan valores de secretos en el repo.**

### TLS de RDS (B-3)

El parameter group fija `require_secure_transport=ON` → RDS **rechaza** conexiones sin cifrar. La app conecta
con TLS estableciendo `DB_SSL_CA` (bundle `rds-combined-ca`); `db/conexion.py` añade `ssl={"ca": ...}` a
PyMySQL/DBUtils. **`DB_SSL_CA` es obligatorio** cuando RDS está activo.

## Recursos deliberadamente NO desplegados

Todos. Esta fase sólo prepara el código. No hay VPC/RDS/S3/ECS/Secrets/CloudWatch/IAM creados. Módulos aún no
incluidos (a añadir al activar): **SQS/DLQ**, **ElastiCache Redis**, **CloudFront + WAF + ACM + Route53**
(dominio) — se incorporan cuando el propietario aporte dominio y decida el alcance.
