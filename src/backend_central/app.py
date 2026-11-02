"""
App Flask del servidor CENTRAL de licencias. Se ejecuta como su PROPIO despliegue, en
infraestructura del fundador, contra su PROPIA base de datos — nunca junto al backend local de un
cliente (`src/backend/app.py`) ni compartiendo base de datos con él. Arrancar:

    DB_HOST=... DB_NAME=smart_manager_central DB_USER=... DB_PASSWORD=... \\
        python -m src.backend_central.app
"""

import logging
import os

logger = logging.getLogger("backend_central.app")


def crear_app_central():
    """Crea la app Flask del servidor central. Importa Flask de forma perezosa (mismo patrón que
    `src.backend.app.crear_app`)."""
    from flask import Flask, jsonify

    try:
        from src.seguridad.entorno import validar_arranque_seguro
        validar_arranque_seguro()
    except RuntimeError:
        raise
    except Exception as e:
        logger.debug("validar_arranque_seguro: %s", e)

    # El esquema local completo (ensure_schema) se reutiliza tal cual para no mantener un
    # bootstrap paralelo — en la BD central solo importan de verdad `codigos_activacion`,
    # `instalaciones_centrales`, `api_dev_apps` y `suscripciones`/`empresa_licencia`/`planes_saas`;
    # el resto de tablas locales quedan simplemente sin usar aquí.
    try:
        from src.db.conexion import ensure_schema
        ensure_schema()
        from src.db.migrador import aplicar_pendientes
        aplicar_pendientes()
    except Exception as e:
        logger.error("No se pudo preparar el esquema de la BD central: %s", e)
        raise

    app = Flask("smart_manager_backend_central")

    @app.get("/salud")
    def salud():
        return jsonify({"estado": "ok", "servicio": "smart-manager-backend-central"})

    from src.backend_central.rutas_licencia import crear_blueprint
    app.register_blueprint(crear_blueprint())

    from src.backend_central.rutas_jobs import crear_blueprint as crear_blueprint_jobs
    app.register_blueprint(crear_blueprint_jobs())

    from src.backend_central.rutas_admin import crear_blueprint as crear_blueprint_admin
    app.register_blueprint(crear_blueprint_admin())

    from src.backend_central.rutas_stripe import crear_blueprint as crear_blueprint_stripe
    app.register_blueprint(crear_blueprint_stripe())

    return app


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("CENTRAL_HOST", "0.0.0.0")
    port = int(os.environ.get("CENTRAL_PORT", "8091"))
    logger.info("Servidor central de licencias escuchando en %s:%s", host, port)
    crear_app_central().run(host=host, port=port)


if __name__ == "__main__":
    main()
