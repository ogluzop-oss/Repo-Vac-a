# ARQUITECTURA AWS OBJETIVO — Smart Manager AI

Arquitectura de referencia (objetivo, **NO provisionada**). Construida SOBRE lo existente (reutilizar → adaptar
→ endurecer → desplegar). No sustituye MariaDB ni la arquitectura multi-tenant.

## Diagrama lógico

```
Internet
  │
Route 53  (app./api./admin.smartmanager.ai)      [🟣 dominio no registrado]
  │
ACM (TLS)  ── CloudFront (CDN, cache estáticos + passthrough SSE) ── AWS WAF
  │
Application Load Balancer (HTTPS, idle timeout ≥ heartbeat SSE)
  │
VPC
  ├─ Subnets públicas: ALB, NAT GW
  └─ Subnets privadas:
       ├─ ECS Fargate — servicio "api"     (Flask/gunicorn, worker async para SSE)
       ├─ ECS Fargate — servicio "worker-ia" (Prophet/forecasting, cola de jobs)   [recomendado]
       ├─ Amazon RDS MariaDB (Multi-AZ)     (reutiliza db/conexion.py + TLS)
       └─ (opcional futuro) ElastiCache Redis / broker  [🟣 solo si multi-instancia SSE]
  │
Amazon S3 (privado, por-tenant)  ←→  CloudFront OAC (documentos vía URL firmada)
AWS Secrets Manager + KMS  (JWT, DB, OAuth, claves cripto)
CloudWatch (logs awslogs + métricas)   ·   CloudTrail (auditoría de plano AWS)
ECR (imágenes)   ·   GitHub Actions (OIDC → ECR → ECS)
```

## Principios de mapeo (reutilización)

| Ya existe en el software | Se adapta a | Sin reemplazar |
|---|---|---|
| `db/conexion.py` (SSL, pool, utf8mb4) | RDS MariaDB | el motor sigue siendo MariaDB |
| `tenant_guard` + `id_empresa` | Igual en AWS + prefijos S3 por tenant | modelo multi-tenant intacto |
| `secret_manager` (backend `vault` extensión) | Secrets Manager + KMS | mismo API `obtener_secreto` |
| `observabilidad` (logs JSON, métricas) | CloudWatch (awslogs) | sistema propio se conserva |
| `dr/*` (backup/pitr/replicación) | RDS snapshots + S3 versioning | lógica de exportación se reutiliza |
| Event Bus + SSE (Fase 4) | 1 servicio ECS (single-instance) | broker sólo si escala horizontal |
| GitHub Actions | + ECR/ECS deploy (OIDC) | pipeline actual se extiende |

## Separación de entornos

DEV (local, MariaDB) · STAGING (cuenta/VPC AWS) · PROD (cuenta/VPC AWS aislada). Roles IAM y secretos por
entorno; nunca compartidos. Ver `AUDITORIA_SEGURIDAD_AWS.md`.

## Notas de diseño críticas

- **SSE**: CloudFront debe reenviar `text/event-stream` sin bufferizar (política de cache deshabilitada para
  `/api/v1/realtime/*`, `X-Accel-Buffering: no`); ALB idle timeout > 15 s (heartbeat). Worker gunicorn async.
- **S3 aislamiento**: clave por objeto `s3://bucket/<id_empresa>/<tipo>/<fichero>`; políticas IAM/condiciones y
  URLs firmadas por tenant; nunca objetos públicos.
- **Prophet**: imagen con cmdstan pesa; separar `worker-ia` evita bloquear la API.
```
