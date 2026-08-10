# AUDITORÍA — ECS / FARGATE (Fase 9)

Objetivo: compatibilidad del backend contenerizado con ECS Fargate. Evidencia: `Dockerfile`,
`docker-compose.prod.yml`, `wsgi.py`.

## Estado actual (real)

- Imagen: `python:3.13-slim`; deps del sistema mínimas (`build-essential`, `libffi-dev`).
- Arranque: `gunicorn -w 4 -b 0.0.0.0:8000 --timeout 60 wsgi:app` → app factory `src.backend.app.crear_app`.
- Puerto: 8000 (`EXPOSE`). `SMART_MANAGER_HEADLESS=1`, `PYTHONUNBUFFERED=1`.
- Copia `src/`, `assets/`, `wsgi.py`. UI PyQt6 **NO** se conteneriza (correcto: sólo backend).

## Clasificación

| Aspecto | Estado | Nota |
|---|---|---|
| Imagen base / Python | 🟢 | slim, apta para Fargate |
| Puerto/EXPOSE | 🟢 | 8000 → target group ALB |
| Stateless (proceso) | 🟡 | el proceso es stateless salvo **escrituras a `documentos/`** (efímero en Fargate) → S3 |
| Usuario | 🟡 | corre como **root** (sin `USER`) → añadir usuario no privilegiado |
| Worker model (SSE) | 🟡 | **sync workers** bloquean con SSE → `--worker-class gevent`/`gthread` + `--worker-connections` |
| Health check | 🟡 | compose usa `/api/v1/live`; confirmar la ruta real registrada bajo `/api/v1` y fijarla en el target group |
| Señales/shutdown | 🟢 | gunicorn maneja SIGTERM (graceful) — adecuado para ECS draining |
| Logs | 🟢 | a stdout (JSON con `SM_LOG_JSON=1`) → driver `awslogs` |
| Variables de entorno | 🟢 | 12-factor; secretos inyectables desde Secrets Manager |
| `.dockerignore` | 🟡 | verificar exclusión de `documentos/`, `.env`, tests, `.git` (reduce imagen/superficie) |
| Prophet/cmdstan | 🟡 | pesa e intensivo en CPU → **servicio worker-ia separado** recomendado |

## Cambios mínimos para Fargate (siguiente fase, NO ahora)

1. `USER` no-root en Dockerfile (crear usuario, `chown /app`).
2. Worker async para SSE (`gunicorn --worker-class gevent -w N`), añadir `gevent` a requirements.
3. Eliminar dependencia de filesystem persistente → capa S3 para `documentos/`.
4. Task definitions: `api` (2+ tareas, autoscaling CPU) y `worker-ia` (Prophet + cola).
5. Secretos vía `secrets` de la task def (Secrets Manager ARNs), no en `environment`.
6. Health check del target group = ruta real (`/api/v1/live` o `/api/v1/health/live`, a confirmar).

**Veredicto: 🟡 REQUIERE ADAPTACIÓN acotada** — no hay incompatibilidad estructural. Ningún 🔴.
