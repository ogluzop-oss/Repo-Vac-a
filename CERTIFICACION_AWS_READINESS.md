# CERTIFICACIÓN — AWS READINESS (Fase 9, honesta)

Fecha 2026-07-27. Fase **exclusivamente de auditoría**: 0 cambios de código, 0 infraestructura, 0 simulación.
Regresión de control: **638 passed, 1 skipped, 0 failed** (sin regresiones). **AWS no está provisionado** →
ningún componente puede marcarse "verificado en AWS real".

## Los tres estados que NO deben confundirse

| Estado | Veredicto |
|---|---|
| **PRODUCTION-READY SOFTWARE** | 🟢 SÍ |
| **AWS PRODUCTION-READY** (software adaptable con cambios acotados) | 🟡 PARCIAL |
| **AWS PRODUCTION-DEPLOYED** | 🔴 NO (sin infraestructura) |

## Matriz final (Fase 21)

Estados: 🟢 verificado en AWS real · 🔵 preparado en software · 🟡 requiere adaptación · 🟣 bloqueado por infra
externa · 🔴 no implementado.

| Área | Estado | Nota |
|---|---|---|
| Docker | 🟡 | non-root + worker async SSE + capa storage |
| ECS/Fargate | 🔵 | task defs por definir; imagen adaptable |
| RDS MariaDB | 🔵 (software 🟢-compatible) | driver/SSL/esquema compatibles; instancia externa |
| S3 | 🟡 | migrar `documentos/` a S3; bucket externo |
| Secrets Manager | 🔵 | punto de extensión `vault`/aws listo |
| KMS | 🔵 | cifrado en reposo a diseñar |
| VPC | 🟣 | externo |
| ALB | 🟡 | timeouts SSE + target group |
| CloudFront | 🟡 | política SSE no-buffer |
| WAF | 🔵 | reglas gestionadas |
| Route 53 | 🟣 | dominio no registrado |
| ACM | 🟣 | requiere dominio |
| CI/CD | 🔵 | CI real; falta OIDC→ECR→ECS |
| CloudWatch | 🔵 | logs JSON/métricas mapeables |
| CloudTrail | 🔵 | complementa auditoría de negocio |
| SSE | 🟡 (1 inst) / 🟣 (N inst) | worker async; broker si escala |
| Multi-tenant | 🟢 (app) / 🔵 (S3/logs) | 404 tablas aisladas, 0 fugas; extender a S3 |
| IA | 🔵 | separar worker-ia; Prophet CPU-intensivo |
| Backups | 🔵 | RDS snapshots + S3 versioning |
| DR | 🟡 / 🟣 | Multi-AZ + cross-region + simulacro real |

## Análisis de riesgos (Fase 16)

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Migración de storage (`documentos/`→S3) incompleta → pérdida/exposición de ficheros | **CRÍTICO** | capa `storage` con doble backend, migración verificada, URLs firmadas + guard tenant |
| Fuga cross-tenant en S3 (firmar sin validar tenant) | **CRÍTICO** | prefijo por `id_empresa` + IAM + reutilizar `tenant_guard`/RBAC en la firma |
| SSE bloquea workers / cae tras CloudFront/ALB | **ALTO** | worker async, timeouts, `X-Accel-Buffering: no`; 1 instancia inicialmente |
| Secretos mal gestionados en el corte a AWS | **ALTO** | Secrets Manager + KMS + rotación; nunca en Git/imagen |
| Downtime en migración de datos | **ALTO** | staging primero, ventana controlada, rollback a snapshot |
| Coste inesperado (NAT/tráfico/CloudWatch) | **MEDIO** | budgets/alarmas, VPC endpoints, retención de logs |
| Prophet consume CPU y degrada la API | **MEDIO** | servicio worker-ia separado + cola |
| Multi-instancia SSE sin broker | **MEDIO** | 1 instancia o sticky hasta introducir broker |
| Parámetros RDS (sql_mode/timezone) divergentes | **BAJO** | parameter group alineado |

## Estimación de costes aproximada (Fase 14, rangos, sin crear recursos)

Órdenes de magnitud mensuales (región tipo eu-west-1; **rangos aproximados, no precios exactos**):

| Escenario | Perfil | Rango orientativo/mes |
|---|---|---|
| **Pequeño** (piloto) | 1-2 tareas Fargate pequeñas, RDS `db.t*` single-AZ, S3 bajo, CloudFront básico | ~ bajo (decenas–pocos cientos de USD) |
| **Medio** (varios tenants) | 2-4 tareas + worker-ia, RDS Multi-AZ mediana, S3/CloudFront moderado, WAF | ~ medio (cientos de USD) |
| **Crecimiento** | autoscaling, RDS mayor + réplica, tráfico/almacenamiento altos, DR cross-region | ~ alto (varios cientos–miles de USD) |

Drivers principales: RDS (Multi-AZ duplica), NAT Gateway + tráfico, Fargate (vCPU/mem × horas), CloudWatch
(ingesta/retención), CloudFront (transferencia). Recomendación: budgets + alarmas desde el día 1.

## Conclusión honesta

- **Qué está listo**: MariaDB (compatible), multi-tenant, seguridad de app, API, observabilidad, CI de calidad.
- **Qué necesita adaptación (código, acotada)**: Docker (non-root/worker async), capa S3, SSE tras CDN/ALB,
  backend AWS de Secrets, separación worker-ia.
- **Qué necesita AWS (externo)**: cuenta, VPC, RDS, S3/KMS, Secrets Manager, ECR/ECS/ALB, Route 53/ACM/WAF,
  CloudFront, broker (si escala SSE), Multi-AZ/DR.
- **Qué debe implementar Claude Code después**: las adaptaciones de código + IaC/plantillas + pipeline OIDC,
  **cuando el propietario provisione AWS y aporte las variables** de `BLOQUEOS_EXTERNOS_AWS_FASE_9.md`.

**No se afirma despliegue en AWS.** Smart Manager AI es **PRODUCTION-READY SOFTWARE** y **AWS-READY con
adaptaciones acotadas**, **NO AWS-DEPLOYED**. Fin de la auditoría — la implementación es un prompt posterior.
