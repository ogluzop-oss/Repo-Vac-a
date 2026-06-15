"""
Backend Flask (server-side): receptor de WEBHOOKS de pago (Fase 3).

Endpoint por proveedor y empresa (multi-tenant):
    POST /webhooks/pagos/<proveedor>/<id_empresa>

Lee el cuerpo CRUDO y las cabeceras (necesarias para validar la firma) y delega
TODO en `src.services.tpv.pagos.webhooks.procesar_webhook`, que valida firma,
evita duplicados/replay, localiza el pedido, actualiza su estado y audita.

Flask se importa de forma perezosa (dentro de `crear_app`) para que el módulo se
pueda importar en escritorio sin tener Flask instalado. Ejecutar como servidor:
    python -m src.backend.app           (PORT, HOST por variables de entorno)
"""

import logging
import os

logger = logging.getLogger("backend.app")


def crear_app():
    """Crea la app Flask con los endpoints de webhooks. Importa Flask aquí
    (lazy) para no exigirlo en despliegues de solo escritorio."""
    from flask import Flask, jsonify, request

    app = Flask("smart_manager_backend")

    @app.get("/salud")
    def salud():
        return jsonify({"estado": "ok", "servicio": "smart-manager-backend"})

    @app.get("/webhooks/pagos/proveedores")
    def proveedores():
        from src.services.tpv.pagos.webhooks import verificadores_registrados
        return jsonify({"proveedores": verificadores_registrados()})

    @app.post("/webhooks/pagos/<proveedor>/<id_empresa>")
    def webhook_pago(proveedor, id_empresa):
        from src.services.tpv.pagos.webhooks import procesar_webhook
        cuerpo = request.get_data() or b""            # bytes crudos (firma)
        cabeceras = dict(request.headers)
        ip = request.headers.get("X-Forwarded-For") or request.remote_addr
        try:
            res = procesar_webhook(proveedor, cabeceras, cuerpo,
                                   id_empresa=id_empresa, ip_origen=ip)
        except Exception as e:                         # nunca filtrar trazas al exterior
            logger.exception("Error procesando webhook %s/%s", proveedor, id_empresa)
            return jsonify({"ok": False, "mensaje": "error interno"}), 500
        http = int(res.pop("http", 200))
        return jsonify(res), http

    return app


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
    logger.info("Backend escuchando en %s:%s", host, port)
    crear_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
