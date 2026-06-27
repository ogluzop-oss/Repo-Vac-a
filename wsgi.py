"""
Punto de entrada WSGI para producción (FASE P2.1).

Uso: gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
Expone `app` (Flask) creado por la app factory, en vez de app.run() (servidor de desarrollo).
"""

from src.backend.app import crear_app

app = crear_app()
