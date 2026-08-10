# Smart Manager AI — imagen del BACKEND SaaS (FASE SAAS-M, preparación cloud).
# La UI de escritorio (PyQt6) NO se conteneriza; esta imagen sirve la API REST/servicios.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SMART_MANAGER_HEADLESS=1

WORKDIR /app

# Dependencias del sistema mínimas para pymysql/cryptography/reportlab.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt* ./
# `gevent` habilita el worker asíncrono necesario para SSE detrás de ALB/Fargate (Fase 10).
RUN pip install --no-cache-dir flask gunicorn gevent pymysql cryptography reportlab python-dotenv requests \
    && (pip install --no-cache-dir -r requirements.txt || true)

COPY wsgi.py gunicorn.conf.py ./
COPY src/ ./src/
COPY assets/ ./assets/

# Endurecimiento (Fase 10): usuario NO privilegiado + propiedad del árbol de la app. El almacenamiento
# persistente va a S3 (STORAGE_BACKEND=s3), por lo que el filesystem del contenedor puede ser de sólo lectura.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/documentos /tmp/smartmanager \
    && chown -R appuser:appuser /app /tmp/smartmanager
ENV TMPDIR=/tmp/smartmanager
USER appuser

EXPOSE 8000

# HEALTHCHECK del contenedor (ECS usa además el del target group del ALB).
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/live').status==200 else 1)" || exit 1

# Arranca el backend Flask (app factory). Worker asíncrono (gevent) para soportar conexiones SSE largas sin
# bloquear peticiones normales. gunicorn gestiona SIGTERM (graceful shutdown → ECS draining). Config en
# gunicorn.conf.py (worker-class/timeouts). El TenantContext aísla por petición.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
