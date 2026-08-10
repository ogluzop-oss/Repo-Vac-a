# AUDITORÍA — DISASTER RECOVERY (Fase 14)

Fecha 2026-07-27. Read-only. Preparación conceptual de DR. **No se valida sobre AWS real (no simulado).**

## Escenarios y preparación

| Escenario de fallo | Estrategia prevista | Software | Infra |
|---|---|---|---|
| Caída de RDS | Multi-AZ failover automático + PITR | 🔵 (`dr_pitr`) | 🟣 Multi-AZ externo |
| Caída de ECS/tarea | ECS reprograma tareas; salud por ALB | 🟢 (stateless + healthcheck) | 🟣 ECS externo |
| Pérdida de instancia | sin estado local persistente (docs→S3, sesión→JWT) | 🟢 | 🟣 |
| Caída de Redis | degradación a single-instance (SSE resincroniza al reconectar) | 🟢 (degradable) | 🟣 |
| Fallo de SQS | reentrega/DLQ; idempotencia evita duplicados | 🟢 | 🟣 |
| Pérdida de región | 2ª región + S3 cross-region replication | 🔵 (`dr_replicacion`) | 🟣 externo |
| Recuperación de documentos | S3 versioning + `migracion`/restore | 🟢 (sw) | 🟣 |
| Restauración completa | RDS snapshot restore + migraciones + S3 | 🔵 | 🟣 |

## Elementos DR

| Elemento | Estado |
|---|---|
| Estrategia Multi-AZ | 🔵 diseñada / 🟣 externa |
| Estrategia DR (cross-region) | 🔵 diseñada / 🟣 externa |
| Procedimiento de recuperación | 🔵 (`dr/*` + `CHECKLIST_DR_PRODUCCION.md`) |
| Rollback | 🔵 (snapshot / task definitions previas) |
| Runbook | 🟡 (existe base; runbook DR de producción a completar con la infra real) |
| Simulacro real (drill) | 🟣 **no ejecutado en AWS** (requisito para certificar DR validado) |

## Honestidad

**DR NO está validado.** Ningún failover/restore/simulacro se ha ejecutado sobre AWS real. La app es
**resiliente por diseño** (stateless, docs en S3, jobs idempotentes, SSE degradable), lo que la hace apta para
un despliegue con DR, pero la validación DR es 🟣 externa y posterior.

## Veredicto

🔵 **DR preparado en software/diseño; resiliencia de la app 🟢**. Multi-AZ/cross-region/simulacro real 🟣
externos. Runbook DR de producción 🟡 a completar. No bloqueante de software.
