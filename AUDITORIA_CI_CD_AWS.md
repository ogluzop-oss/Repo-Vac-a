# AUDITORÍA — CI/CD hacia AWS (Fase 9)

Objetivo: preparación del pipeline actual (GitHub Actions) para build→ECR→ECS. **No configurar despliegue.**

## Estado actual (real)

`.github/workflows/`:
- `ci.yml`: **lint** (Ruff, no bloqueante) · **i18n** (valida JSON de idiomas + paridad es/en) · **tests**
  (pytest REAL sobre servicio MariaDB levantado en el job).
- `tests.yml`, `multiplataforma.yml`: suites adicionales.
- Build del `.exe` de escritorio: plantilla comentada (fase posterior).

## Objetivo de pipeline (diseño)

```
push/PR → lint + i18n + tests (MariaDB) ──▶ [main] build imagen Docker
                                              │
                                     OIDC → ECR (push tag inmutable)
                                              │
                                     Deploy STAGING (ECS update-service)
                                              │
                                     Smoke test (/api/v1/health/ready + login)
                                              │
                                     Approval manual (environment protegido)
                                              │
                                     Deploy PROD (ECS) + tag release + rollback listo
```

## Adaptaciones necesarias (siguiente fase)

| Elemento | Estado | Acción |
|---|---|---|
| Tests en CI | 🟢 | ya reales sobre MariaDB; reutilizar como gate |
| Autenticación a AWS | 🔵 | **GitHub OIDC → rol `sm-ci-deploy`** (sin claves estáticas en secrets) |
| Build/push imagen | 🔵 | `docker build` + push a **ECR** con tag inmutable (SHA) |
| Deploy | 🔵 | `aws ecs update-service` / task def nueva; **STAGING auto**, **PROD con approval** |
| Smoke test | 🔵 | golpear `/api/v1/health/ready` + un login tras deploy |
| Rollback | 🔵 | mantener N task definitions previas; revertir a la anterior |
| Versionado/release | 🟡 | tags de release + changelog; hoy no formalizado |
| Secrets del pipeline | 🟢 (política) | sólo ARNs/roles vía OIDC; nunca secretos en el repo |

**Veredicto: 🔵 PREPARADO** — el CI de calidad existe y es real; falta el tramo de entrega a AWS (OIDC/ECR/ECS),
que se implementa cuando exista la cuenta AWS. Ningún 🔴.
