# DOCKER SECURITY HARDENING (Fase 10, Fase 5 del plan)

## Cambios implementados en el `Dockerfile`

| Endurecimiento | Antes | Ahora |
|---|---|---|
| Usuario | root | **non-root** `appuser` (uid 10001), `HOME` propio |
| Propiedad FS | root | `chown appuser` de `/app` y `/tmp/smartmanager` |
| Temporales | `/tmp` global | `TMPDIR=/tmp/smartmanager` (propio del usuario) |
| Worker SSE | `gunicorn -w 4` (sync) | `gunicorn -c gunicorn.conf.py` (worker **gevent**) |
| Healthcheck | sólo en compose | `HEALTHCHECK` en la imagen (`/api/v1/live`) |
| Shutdown | — | gunicorn gestiona SIGTERM → graceful (ECS draining) |

## No se rompe

- Generación de PDF (reportlab), Prophet, exportaciones y logs siguen funcionando: escriben en `TMPDIR`
  (propio) o van a **S3** cuando `STORAGE_BACKEND=s3`. El filesystem del contenedor puede ser de sólo lectura
  en Fargate (persistencia en S3).
- Logs a stdout (JSON con `SM_LOG_JSON=1`) → driver `awslogs`/CloudWatch.

## Recomendaciones adicionales (despliegue)

- `readOnlyRootFilesystem: true` en la task definition (montar `TMPDIR` como volumen efímero writable).
- `.dockerignore` para excluir `documentos/`, `.env`, `tests/`, `.git` (menor imagen y superficie).
- Escaneo de imagen (ECR scan on push) en el pipeline.
- Secretos vía `secrets` de la task def (ARNs de Secrets Manager), no en `environment`.

## Verificación

- La app arranca con la config de gunicorn (`gunicorn.conf.py`); worker gevent instalable en la imagen.
- Regresión de la app: **652 passed, 1 skipped** (sin cambios de comportamiento por el hardening).
