# AUDITORÍA — Seguridad AWS (Fase 9)

Objetivo: preparar el mapeo de seguridad a IAM/VPC/KMS/Secrets Manager/CloudTrail/WAF, conservando la
seguridad de aplicación existente (RBAC, MFA, WebAuthn, auditoría, tenant_guard). **No crear roles reales.**

## Seguridad de aplicación existente (se conserva)

- **RBAC** (`services.autorizacion.puede`, catálogo de permisos) · **MFA TOTP** + **WebAuthn** · **auditoría**
  (`log_auditoria`) · **tenant_guard** (analiza SQL sin filtro de tenant) · **Secret Manager** con backend
  `fernet` y punto de extensión `vault`.
- Secretos NO en Git: `.env.*.example` sólo placeholders `<desde-secret-store>` + marcas `[EXTERNO]`.

## Clasificación de variables (para Secrets Manager / config)

| Variable | Clase | Destino AWS |
|---|---|---|
| `DB_PASSWORD` | Credencial | Secrets Manager (+ rotación) |
| `SMART_MANAGER_JWT_SECRET` | Secreto | Secrets Manager (rotable, único por entorno) |
| `SM_SECRET_BACKEND` | Configuración | env (valor `vault`/aws en prod) |
| `DB_SSL_CA/CERT/KEY` | Certificado | Secrets Manager / fichero montado |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET` | Credencial (3ª parte) | Secrets Manager |
| `documentos/.correo_key` | Clave criptográfica | Secrets Manager + KMS |
| `API_CORS_ORIGINS`, `DB_HOST/PORT/NAME/USER` | Configuración | env / Parameter Store |
| Claves de datos (cifrado en reposo) | Clave criptográfica | **KMS** (CMK por entorno) |

## Matriz IAM objetivo (mínimo privilegio) — DISEÑO, no provisión

| Componente | IAM Role | Permisos | Recursos | Riesgo |
|---|---|---|---|---|
| ECS task (api) | `sm-api-task` | leer secretos concretos, RW S3 por prefijo tenant, put logs/métricas | Secrets ARNs, bucket/*, log group | Medio (acceso a datos) |
| ECS task (worker-ia) | `sm-worker-task` | leer secretos, RW S3, RDS connect | Secrets, bucket, RDS | Medio |
| ECS execution role | `sm-exec` | pull ECR, escribir logs, leer secretos de arranque | ECR, log group, Secrets | Alto (arranque) |
| RDS | (SG, no role app) | acceso sólo desde SG de ECS | RDS endpoint | Alto (datos) |
| CI/CD (GitHub OIDC) | `sm-ci-deploy` | push ECR, update ECS service, describe | ECR repo, ECS cluster/service | Alto (deploy) |
| KMS | política de clave | encrypt/decrypt para roles anteriores | CMK | Alto (cifrado) |

## Red (VPC) — diseño

- **Subnets públicas**: ALB, NAT Gateway. **Subnets privadas**: ECS, RDS (sin IP pública), broker futuro.
- **Security Groups**: ALB→ECS (8000), ECS→RDS (3306), ECS→S3/Secrets (endpoints VPC), egress mínimo.
- **VPC endpoints** para S3/Secrets Manager/ECR/CloudWatch → tráfico privado sin NAT.

## Auditoría de plano AWS

- **CloudTrail** cubre acciones de la cuenta AWS (complementa `log_auditoria` de negocio, que se conserva).

## Separación de entornos

DEV/STAGING/PROD con cuentas o VPCs separadas, roles y secretos independientes; CI despliega a STAGING
automáticamente y a PROD con aprobación manual.

**Veredicto: 🔵 diseño de seguridad AWS preparado; 🟣 provisión (IAM/VPC/KMS/Secrets) externa.** La seguridad
de aplicación es 🟢 y no se sustituye.
