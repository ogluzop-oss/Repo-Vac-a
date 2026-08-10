# AUDITORÍA OBSERVABILIDAD AWS — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay CloudWatch ni infraestructura desplegada.**

## Software (verificado)

🟢 `services/observabilidad`: `health` (`/live|/ready|/health`), `metricas`, `tracing`, `correlation`,
`alertas_tecnicas`, `dashboards`, `operacional`, `cloud/` (distributed tracing). Logs JSON (`SM_LOG_JSON`) →
stdout (compatible driver `awslogs`).

## Validación en AWS (Fase 15.10)

🟣 **BLOQUEADA**. No existe evidencia real en AWS: no hay log groups CloudWatch, ni métricas/alarmas reales, ni
health checks corriendo en el servicio. **No se declara observabilidad operativa a partir del código.**

## Alarmas a crear (cuando exista infra)

5xx, CPU, memoria, RDS (conexiones/latencia), SQS backlog, DLQ, Redis, latencia de endpoints, health checks.

## Resume

Provisionar CloudWatch (log groups `awslogs`, métricas, alarmas). Validar evidencia real (logs/alarmas
disparando). Estado: 🟢 software / 🟣 evidencia AWS externa.
