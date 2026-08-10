# ARQUITECTURA — DOCKER HARDENING (Fase 10)

Ver el detalle e implementación en **`DOCKER_SECURITY_HARDENING.md`**.

Resumen: la imagen del backend se endurece para ECS/Fargate — usuario **non-root** (`appuser` uid 10001),
`TMPDIR` propio, `HEALTHCHECK` en la imagen, worker **gevent** para SSE (`gunicorn.conf.py`), graceful shutdown
por SIGTERM. Persistencia de documentos en **S3** (`STORAGE_BACKEND=s3`) → filesystem del contenedor puede ser
de sólo lectura. Sin romper PDF/Prophet/exportaciones/logs. Estado: 🟢 implementado.
