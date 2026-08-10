# AUDITORÍA CI/CD — FASE 15

Fecha 2026-07-27. **BLOQUEADO para CD real: sin ECR/ECS ni credenciales AWS.**

## Software (verificado)

🟢 CI real (GitHub Actions): lint (Ruff) + i18n + tests sobre MariaDB. 🔵 CD documentado (plantilla OIDC→ECR→
ECS→smoke→approval→prod).

## Validación en AWS (Fase 15.17)

🟣 **BLOQUEADA / NO EJECUTADO**. No probado: build→ECR real, deploy a staging/prod, smoke post-deploy, approval,
**rollback real**. **No se declara CD operativo por existir un YAML.**

## Resume

Configurar proveedor OIDC + rol `sm-ci-deploy`; extender workflows (build→push ECR con tag SHA inmutable →
`ecs update-service` → smoke `/health/ready` → approval → prod → rollback a task def previa). Ejecutar al menos
un deploy + un rollback reales. Variables: `AWS_ROLE_ARN`, `ECR_REPO`, `ECS_SERVICE`. Sin tag `latest` como
release. Estado: 🟢 CI / 🔵 CD preparado / 🟣 validación externa.
