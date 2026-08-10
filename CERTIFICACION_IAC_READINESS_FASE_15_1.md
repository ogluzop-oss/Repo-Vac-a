# CERTIFICACIÓN — Preparación de la IaC AWS para iniciar Fase 15.1

Fecha 2026-07-29. Auditoría final de solo lectura. **No se desplegó nada** (no `terraform apply/destroy/import`,
no AWS CLI de creación, no `cdk deploy`, no `docker push`). AWS Organizations e IAM Identity Center **no
tocados**. Todos los `enable_*` permanecen en `false`.

## Estado final: ✅ LISTO para iniciar Fase 15.1

## Verificación de los 13 puntos

| # | Área | Resultado |
|---|---|---|
| 1 | Terraform modular | ✅ único `terraform{}` (versions.tf); 7 módulos cableados; outputs válidos |
| 2 | Variables y outputs | ✅ entradas de módulo coinciden con las llamadas; outputs con `try()` |
| 3 | DEV/STAGING/PROD | ✅ tfvars por entorno; CIDRs 10.20/10.30/10.40; prod `multi_az=true`; nombres `${project}-${env}` |
| 4 | Backend / state isolation | ✅ `.tfbackend.example` por entorno (key distinta); backend comentado (no creado) |
| 5 | Secrets Manager | ✅ `SM_SECRET_PREFIX` casa con `${name}/`; sin valores de secretos |
| 6 | RDS MariaDB | ✅ InnoDB/utf8mb4/UTC; `require_secure_transport=ON`; privado; KMS; TLS compatible con la app |
| 7 | S3 | ✅ privado + Block Public Access + SSE-KMS + versioning + lifecycle; casa con StorageProvider |
| 8 | VPC/network | ✅ subnets públicas/privadas, NAT, SG de app |
| 9 | CloudWatch | ✅ log groups (api/worker) + alarma base |
| 10 | ECR/ECS/Fargate | ✅ ECR+cluster+ALB+target group (task def/service diferidos **a propósito**, no en 15.1) |
| 11 | Dockerfile | ✅ non-root, HEALTHCHECK `/api/v1/live` (válido), gevent |
| 12 | GitHub Actions | ✅ plan-only; `apply/destroy/import` nunca activos |
| 13 | Compatibilidad app↔infra | ✅ SM_SECRET_PREFIX, DB_SSL_CA/PyMySQL, StorageProvider/S3, health endpoint |

## Comprobaciones específicas A–H

- **A. SM_SECRET_PREFIX** — ✅ coincide: módulo `secrets` nombra `${project}-${env}/<CLAVE>`; app resuelve
  `SM_SECRET_PREFIX=smart-manager-<env>/` + clave → mismo `SecretId`.
- **B. `/api/v1/live`** — ✅ ruta REAL (`backend/api.py:190` → `health.live()` = `{"status":"ok"}`, HTTP 200).
  **No modificado.**
- **C. `require_secure_transport=ON`** — ✅ compatible: `db/conexion.py` añade `ssl={"ca": DB_SSL_CA}` a
  PyMySQL/DBUtils. Obligatorio fijar `DB_SSL_CA` (bundle rds-combined-ca) cuando RDS esté activo.
- **D. Backend por entorno sin crearlo** — ✅ configuración parcial documentada + `.tfbackend.example` por
  entorno con key distinta; backend comentado (no se crea bucket/DynamoDB).
- **E. Recursos desactivados** — ✅ 7/7 `enable_*=false` en variables.tf y en los 3 tfvars.
- **F. Workflow no puede `apply`** — ✅ sólo `fmt/init -backend=false/validate`; `plan`/`apply` comentados.
- **G. Sin secretos reales** — ✅ 0 (RDS `manage_master_user_password`; `secrets` sin `secret_version`; env sólo
  placeholders/config).
- **H. Sin errores de arquitectura** — ✅ ninguno que impida iniciar 15.1.

## Bloqueantes reales
**NINGUNO.**

## Correcciones obligatorias antes de Fase 15.1
**NINGUNA.** La Fase 15.1 (provisionar VPC/secrets/S3/RDS/observabilidad) usa módulos completos.

## Correcciones que pueden esperar (alcance de despliegue posterior, NO bloquean 15.1)
- **A-3** — Completar task definition/service ECS + listener HTTPS (ACM) — **diferido a propósito** (el propio
  prompt pide no completar el end-to-end de ECS aún).
- **B-2** — Gestionar el proveedor OIDC de GitHub existente (`data`/`import`) para evitar colisión.
- **B-6** — Acotar `resources=["*"]` del rol CI a ARNs concretos de ECR/ECS.
- **B-5** — Ejecutar `terraform fmt -recursive` (propietario) antes de confiar en el gate `fmt -check`.
- Módulos futuros (aún NO): **SQS+DLQ**, **ElastiCache Redis**, **CloudFront+WAF+ACM+Route53**.

## Confirmación
No se desplegó ningún recurso AWS. No se modificó Organizations ni Identity Center. No se crearon cuentas ni
STAGING/PROD. Regresión de software estable (669 passed, 1 skipped). **No se modificó código** (no se halló
ningún bloqueante).
