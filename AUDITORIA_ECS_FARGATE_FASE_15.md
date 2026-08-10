# AUDITORÍA ECS/FARGATE — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay Docker daemon, ECR ni ECS.**

## Software (verificado)

🟢 `Dockerfile` endurecido: non-root (`appuser` uid 10001), `HEALTHCHECK`, `gevent`, `gunicorn.conf.py`
(worker async SSE, keepalive/timeouts), SIGTERM/graceful. App stateless (docs→S3, sesión→JWT). `/health/live|
ready|version`.

## Validación en AWS (Fase 15.5)

🟣 **BLOQUEADA**. No ejecutado: build de imagen (Docker daemon ausente), push a ECR, despliegue en ECS/Fargate,
task definitions, autoscaling, ALB target group, validación de readiness/liveness contra el servicio real,
conexión a RDS/Secrets/S3/SQS/Redis desde la tarea.

## Resume

Instalar Docker; provisionar ECR + cluster ECS + servicios `api`/`worker-ia` + ALB. Build reproducible con
commit SHA. Variables: `ECR_REPO`, `ECS_CLUSTER`, `ECS_SERVICE`, `ALB_ARN`, `TASK_CPU/MEM`, secretos vía task
def (ARNs Secrets Manager, no texto plano). No enviar tráfico hasta readiness OK. Estado: 🟢 software / 🟣
validación externa.
