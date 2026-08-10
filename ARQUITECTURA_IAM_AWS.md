# ARQUITECTURA — IAM AWS (Fase 10)

Diseño de roles de mínimo privilegio. **No se crean roles reales** (🟣 externo). Complementa
`AUDITORIA_SEGURIDAD_AWS.md`.

## Roles y permisos (mínimo privilegio)

| Rol | Permisos | Recursos | Riesgo |
|---|---|---|---|
| **ECS Task — api** | `s3:GetObject/PutObject/DeleteObject` (prefijo tenant), `secretsmanager:GetSecretValue` (secretos concretos), `sqs:SendMessage`, `kms:Decrypt`, logs | bucket/*, secretos, cola, CMK | Medio |
| **ECS Task — worker-ia** | `sqs:ReceiveMessage/DeleteMessage/GetQueueAttributes`, `s3:*Object` (prefijo tenant), `secretsmanager:GetSecretValue`, `kms:Decrypt`, RDS connect | cola, bucket, secretos, RDS | Medio |
| **ECS Execution role** | `ecr:GetDownloadUrl/BatchGetImage`, `logs:CreateLogStream/PutLogEvents`, leer secretos de arranque | ECR, log group, secretos | Alto |
| **Migration role** | DDL sólo sobre la BD de la app | RDS | Alto |
| **CI/CD (GitHub OIDC)** | `ecr:*` (push), `ecs:UpdateService/DescribeServices/RegisterTaskDefinition` | repo ECR, cluster/servicio | Alto |
| **RDS** | acceso sólo desde SG de ECS (no rol de app) | endpoint RDS | Alto |
| **KMS (política de clave)** | `Encrypt/Decrypt/GenerateDataKey` a las task roles | CMK | Alto |

## Principios

- Un rol por función; sin comodines de recurso salvo prefijo por tenant en S3.
- CI se autentica por **OIDC** (sin claves estáticas en GitHub).
- RDS y ElastiCache sin IP pública; acceso por Security Group desde ECS.
- Separación DEV/STAGING/PROD (cuentas o VPCs distintas), roles y secretos independientes.

Estado: 🔵 diseño listo · 🟣 provisión externa.
