# RUNBOOK — Monitorización y Recuperación de Incidencias (AWS)

## Observabilidad (CloudWatch)

- **Logs**: la app emite JSON a stdout (`SM_LOG_JSON=1`) → driver `awslogs` → log groups `/<name>/api`,
  `/<name>/worker-ia` (retención por entorno).
- **Métricas/Alarmas** (módulo `observability`):
  - ALB `HTTPCode_Target_5XX_Count` > 5 (1 min).
  - ECS `CPUUtilization` > 85% (si se conecta el servicio).
  - RDS `CPUUtilization` > 80% (si se conecta la instancia).
  - Dashboard `<name>-overview`.
- **Alarmas a añadir al desplegar**: latencia p95, memoria ECS, RDS free storage/connections, SQS backlog/DLQ
  (cuando exista SQS), health-check unhealthy.
- **CloudTrail**: auditoría del plano AWS (complementa `log_auditoria` de negocio).

## Señales clave a vigilar

| Síntoma | Métrica | Acción |
|---|---|---|
| Errores 5xx | ALB 5XX | revisar logs de la tarea; ¿deploy reciente? → rollback |
| Latencia alta | TargetResponseTime | ¿RDS saturada? ¿autoscaling? |
| Tareas unhealthy | TargetGroup HealthyHostCount | revisar `/api/v1/health/ready` (¿BD/secretos?) |
| CPU/memoria alta | ECS CPU/Mem | autoscaling; revisar carga/consultas |
| RDS saturada | RDS CPU/Connections | pool/consultas; escalar instancia |
| DLQ con mensajes | SQS DLQ (futuro) | jobs venenosos; revisar `worker`/idempotencia |

## Recuperación de incidencias (playbook)

1. **Detectar**: alarma CloudWatch / health-check en rojo.
2. **Contener**: si es un deploy reciente → **rollback** a la task definition anterior (ver runbook rollback).
3. **Diagnosticar**: logs CloudWatch de la tarea (correlation IDs), estado de RDS/Secrets, `/api/v1/health`.
4. **Mitigar**: escalar (autoscaling/instancia), reiniciar tareas (`update-service --force-new-deployment`).
5. **Recuperar datos** si aplica: restore RDS/S3 (ver runbook DR).
6. **Post-mortem**: registrar causa, RPO/RTO reales, acciones correctivas.

## Salud de la aplicación (endpoints)

- `/api/v1/live` (liveness, 200), `/api/v1/ready` (readiness, 200/503 según BD), `/api/v1/health`,
  `/api/v1/metrics` (Prometheus). El ALB usa `/api/v1/live` como health-check del target group.

## Contactos / escalado
Definir on-call y canal de alertas (SNS → email/Slack) al provisionar (`alarm_sns_topic_arn` en el módulo
`observability`).
