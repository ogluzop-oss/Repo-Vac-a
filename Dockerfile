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
RUN pip install --no-cache-dir flask gunicorn pymysql cryptography reportlab python-dotenv requests \
    && (pip install --no-cache-dir -r requirements.txt || true)

COPY wsgi.py ./
COPY src/ ./src/
COPY assets/ ./assets/

EXPOSE 8000

# Arranca el backend Flask (api.py vía app factory). El TenantContext aísla por petición.
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "60", "wsgi:app"]
