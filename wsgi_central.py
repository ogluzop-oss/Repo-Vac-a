"""
Punto de entrada WSGI del servidor CENTRAL de licencias (Fase 2/5, ver plan `hazy-riding-aurora`).
Despliegue SEPARADO del backend local (`wsgi.py`): propia imagen (`Dockerfile.central`), propia
infraestructura, propia base de datos — nunca comparte proceso ni esquema con el backend de un
cliente. Expone `app` (Flask) vía la app factory, igual que `wsgi.py`.

Uso: gunicorn -c gunicorn.conf.py wsgi_central:app
"""

from src.backend_central.app import crear_app_central

app = crear_app_central()
