# CHECKLIST — DESPLIEGUE A PRODUCCIÓN

Marca: ☐ pendiente · 🟢 software listo · 🟣 requiere provisionado externo.

## Preparación
- 🟢 `.env.production` creado desde `.env.production.example` (secretos desde secret store, NO en Git).
- 🟣 Cuenta cloud + proyecto/tenant cloud provisionados. [EXTERNO]
- 🟣 MariaDB productiva (con backups automáticos + replicación) provisionada. [EXTERNO]
- 🟣 Object storage privado (`SM_OBJECT_STORAGE_URL`) + CDN para recursos públicos. [EXTERNO]
- 🟣 Dominios (app./api./admin.) + DNS + certificados TLS. [EXTERNO]

## Build & release
- 🟢 Imagen construida con tag versionado (`VERSION`/`COMMIT_SHA`/`RELEASE_TAG`), **no `latest`**.
- 🟢 `docker-compose.prod.yml` o manifiestos del orquestador parametrizados por entorno.
- 🟣 Registro de imágenes (push/pull) + runner de CD con credenciales. [EXTERNO]

## Migraciones (orden seguro)
1. 🟢 **Backup previo** (`dr/backup_operacional`).
2. 🟢 `migrador.aplicar_pendientes()` (idempotente; migraciones destructivas documentadas y NO automáticas).
3. 🟢 `GET /health/ready` → 200 antes de recibir tráfico.
4. 🟢 Smoke test (endpoints críticos + login + un flujo de negocio).
5. 🟢 Rollback disponible (imagen anterior + restore de backup si procede).

## Post-despliegue
- 🟢 `/health/live` 200, `/health/ready` 200, `/health/version` correcto.
- 🟢 Observabilidad activa (métricas/alertas/tracing); logs sin secretos.
- 🟢 Enforcement SaaS operativo (planes/límites/suspensión).
- 🟢 API pública OAuth2 accesible con OpenAPI publicado.

## Gates (no desplegar si…)
- Tests o migraciones en rojo · health check en rojo · vulnerabilidad crítica · sin aprobación explícita.
