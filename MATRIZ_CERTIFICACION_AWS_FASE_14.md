# MATRIZ DE CERTIFICACIÓN — PRE-DESPLIEGUE AWS (Fase 14)

Fecha 2026-07-27. Estados: 🟢 VERIFICADO (software/tests) · 🟡 PARCIAL · 🔴 BLOQUEANTE · 🟣 EXTERNO · 🔵
PREPARADO. Regresión: **669 passed, 1 skipped, 0 failed**.

| Área | Estado | Evidencia | Bloqueo |
|---|---|---|---|
| Código AWS-ready | 🟢 | 669 passed; N7 (1 forecasting, 1 hub) | — |
| RDS | 🟢 sw / 🟣 | InnoDB/utf8mb4, SSL-ready, sin SUPER/triggers | instancia real |
| Migración DB | 🟢 tenant / 🟡 / 🟣 | export/import round-trip probado; runbook cutover full-DB a formalizar | RDS real |
| S3 | 🔵 / 🟣 | `S3StorageProvider` (SSE-KMS, presigned) | bucket real |
| Storage | 🟢 | CREATE/READ/DOWNLOAD/DELETE/LEGACY/VISOR + tenant/RBAC | — |
| Redis | 🟢 sw / 🟣 | sin self-echo (`InProcessBroker`) | Redis real |
| SSE | 🟢 sw / 🟣 | JWT+tenant+heartbeat+gevent | ALB/CloudFront |
| SQS | 🔵 / 🟣 | confirmar/rechazar+visibility+DLQ | cola real |
| Idempotencia | 🟢 | reclamo atómico (migr 0165) | multi-worker SQS real 🟣 |
| IA Worker | 🟢 | motor único; reutiliza forecasting/retraining | — |
| Secrets | 🟢 sw / 🟣 | backend AWS, sin fallback inseguro; 0 secretos en Git | Secrets Manager real |
| Docker | 🟢 sw / 🟣 | non-root, HEALTHCHECK, gevent, SIGTERM | daemon/build externo |
| ECS/Fargate | 🔵 / 🟣 | stateless + healthcheck + docs task defs | cluster real |
| IAM | 🟢 (diseño) / 🟣 | mínimo privilegio; sin wildcards | roles reales |
| Terraform | 🟢 sintaxis / 🟣 | HCL válido (estático) | `terraform` no instalado |
| Observabilidad | 🟢 sw / 🔵 | health/metrics/tracing/alertas | CloudWatch |
| Backup | 🟢 tenant / 🔵 / 🟣 | export/restore round-trip; RDS/S3 mapeados | RDS/S3 reales |
| DR | 🔵 / 🟡 / 🟣 | `dr/*`; resiliencia app 🟢; runbook 🟡 | Multi-AZ/cross-region/simulacro |
| Seguridad | 🟢 | 0 vulnerabilidades críticas; RBAC/MFA/WebAuthn/tenant | controles infra 🟣 |
| Multi-tenant | 🟢 | guard base + BD; tests A≠B | — |
| Entitlements Fase 16 | 🔵 | resolver central `saas/licensing`+`enforcement`; **0 gating disperso** | implementación diferida |

## Resumen

- **Software**: 🟢 sin bloqueantes. Todo lo que puede verificarse localmente está verificado.
- **Pendientes 🟡 (no bloqueantes de software, operativos)**: runbook de cutover full-DB, valores SLA RPO/RTO
  finales, runbook DR de producción.
- **Externos 🟣**: toda la infraestructura AWS + Terraform CLI + Docker daemon + validaciones sobre AWS real.
- **Bloqueantes 🔴**: **ninguno**.
