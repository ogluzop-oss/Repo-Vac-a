# PLAN DE DESPLIEGUE AWS (Fase 10 → despliegue futuro)

Con el software ya **AWS-ready**, el despliegue real es un paso posterior (requiere AWS provisionado). Este
plan enlaza con `PLAN_MIGRACION_AWS.md` (Fase 9) y `BLOQUEOS_EXTERNOS_AWS_FASE_9.md`.

## Precondiciones del propietario (🟣 externo)

Cuenta AWS, VPC, RDS MariaDB, S3+KMS, Secrets Manager, ECR, ECS Fargate, ALB, (opcional) SQS, (opcional)
ElastiCache Redis, Route 53/ACM/WAF/CloudFront. Credenciales por IAM Role/OIDC (nunca en Git).

## Secuencia

1. **Config**: `STORAGE_BACKEND=s3`, `SM_SECRET_BACKEND=aws_secrets_manager`, `JOB_QUEUE_BACKEND=sqs`,
   `GUNICORN_WORKER_CLASS=gevent`, variables AWS (ver `.env.production.example`).
2. **Imagen**: build (Dockerfile hardened) → push a ECR (pipeline OIDC).
3. **RDS**: crear instancia, parameter group utf8mb4/UTC, TLS; aplicar migraciones (rol de migración).
4. **S3/Secrets/KMS**: bucket privado + CMK; crear secretos (JWT/DB/OAuth/correo_key); migrar ficheros
   (`storage.migracion`, no destructivo).
5. **ECS**: servicios `api` (gevent) + `worker-ia` (SQS); autoscaling; secrets en task def; ALB target group
   (health `/api/v1/live`, idle timeout > 15 s).
6. **Front**: CloudFront (política SSE no-buffer) + WAF + ACM + Route 53 (app./api./admin.).
7. **SSE multi-instancia** (si se escala): ElastiCache Redis + `RedisDistribution` + `set_distribucion`.
8. **Pruebas**: smoke (`/api/v1/health/ready` + login), E2E, **SSE tras CloudFront**, **aislamiento tenant**
   (S3/eventos/jobs).
9. **Producción**: deploy con approval; tag release; runbook de rollback (task definitions previas).
10. **DR**: Multi-AZ + S3 cross-region + retención; **simulacro real** → evidencia para certificar DR.

## Qué hace Claude Code vs el propietario

- **Claude Code** (fase de despliegue): completar módulos IaC, task definitions, pipeline OIDC→ECR→ECS,
  scripts de migración/smoke, activar backends AWS por config.
- **Propietario**: provisionar recursos, credenciales/roles, dominios/certificados, aprobar go-live.

## Honestidad

Nada se declara operativo hasta existir y probarse en AWS real. Hoy: **AWS PRODUCTION-READY SOFTWARE 🟢**,
**AWS PRODUCTION-DEPLOYED 🔴**.
