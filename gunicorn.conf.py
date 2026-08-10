"""
Configuración de gunicorn para producción AWS (Fase 10).

SSE (endpoint `/api/v1/realtime/stream`) usa conexiones HTTP largas: con workers SÍNCRONOS cada conexión
bloquea un worker. Por eso se usa la clase de worker **gevent** (asíncrona), que soporta miles de conexiones
concurrentes (incluidas las SSE) sin bloquear las peticiones normales. Reutiliza la app WSGI existente
(`wsgi:app`); no cambia la lógica de la aplicación.

Todos los valores son configurables por entorno para ECS/Fargate.
"""

import multiprocessing
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
# Async worker imprescindible para SSE detrás de ALB/CloudFront.
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gevent")
workers = int(os.getenv("GUNICORN_WORKERS", str(multiprocessing.cpu_count() * 2 + 1)))
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))
# timeout alto/0 para no matar conexiones SSE largas (el heartbeat de 15 s las mantiene vivas).
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "75"))     # > idle timeout típico de ALB
accesslog = os.getenv("GUNICORN_ACCESSLOG", "-")           # stdout → awslogs/CloudWatch
errorlog = os.getenv("GUNICORN_ERRORLOG", "-")
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
