# AUDITORÍA — TERRAFORM IaC (Fase 11, post-corrección H4)

Fecha 2026-07-27. Estado tras corregir el HCL inválido detectado en la Auditoría Final de Fase 10.

## Defecto original (H4)

`infra/aws/main.tf` declaraba variables con argumentos separados por coma
(`variable "x" { type = string, default = ... }`) — HCL no lo admite; `terraform validate` fallaría.

## Corrección implementada 🟢

- Las variables usan ahora un argumento por línea (HCL válido):
  ```hcl
  variable "aws_region" {
    type    = string
    default = "eu-west-1"
  }
  ```
- Sin secretos, sin `AWS_ACCESS_KEY_ID`/`SECRET`, sin valores de producción hardcodeados.
- El fichero sigue siendo un **skeleton** (declara `terraform`/`provider`/variables + comentarios de los
  módulos objetivo: VPC, RDS, ECS, ECR, ALB, S3, KMS, Secrets Manager, CloudFront, Route53, ACM, WAF,
  CloudWatch, SQS, DLQ, Redis). No crea recursos ficticios para aparentar despliegue.

## Validación

| Verificación | Estado |
|---|---|
| Sin argumentos separados por coma | 🟢 `test_h4_hcl_sin_comas_invalidas` + grep |
| Bloques `terraform`/`provider`/`variable` presentes | 🟢 |
| `terraform fmt` / `terraform validate` | 🟣 **BLOQUEADO — terraform NO instalado en el entorno** |

## Bloqueo externo (regla de detención)

1. **Recurso**: binario `terraform` (y opcionalmente credenciales AWS para `plan`).
2. **Motivo**: no está instalado en este entorno → no se puede ejecutar `terraform validate`.
3. **Proveedor**: HashiCorp Terraform CLI.
4. **Qué debe hacer el propietario**: instalar Terraform y ejecutar `terraform init && terraform fmt -check &&
   terraform validate` en `infra/aws/` (sin `apply`).
5. **Variables**: `AWS_REGION`, `AWS_ACCOUNT_ID` (para `plan`/`apply` posteriores; nunca en Git).
6. **Qué hará Claude Code después**: completar los módulos de recursos (VPC/RDS/ECS/S3/…) con HCL válido y
   revisar el `plan`.
7. **Estado**: HCL corregido 🟢; validación con terraform 🟣 externa; recursos reales 🟣 externos.

## Estado

Sintaxis **corregida**; `terraform validate` pendiente de ejecutar (herramienta externa no disponible). El
skeleton es coherente y ampliable; no se despliega nada.
