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
import sys
import time

logger = logging.getLogger("backend.app")

_INICIADO_EN = time.time()   # capturado al IMPORTAR este módulo — usado por `src.main.iniciar_backend`
                             # para distinguir un backend embebido obsoleto (huérfano de una sesión
                             # de desarrollo anterior) de uno arrancado con el código actual.
_RAIZ_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../src


def _codigo_propio_desactualizado() -> bool:
    """¿Alguno de los módulos de `src/` que ESTE proceso ya tiene cargados (`sys.modules`) se
    modificó en disco DESPUÉS de que este backend arrancara?

    Antes, `src.main.iniciar_backend` comparaba `_INICIADO_EN` contra el `.py` más reciente de
    TODO `src/` — así, cualquier edición en un fichero que el backend ni siquiera importa (p. ej.
    `src/gui/*`, que el backend nunca toca) lo invalidaba igual, forzando un mata-y-relanza en
    cada arranque de la app durante una sesión de desarrollo activa (bug real reportado: "no
    quiero que se cierren los procesos antiguos y se reabran desde cero").

    El backend se auto-diagnostica en vez de depender de una lista de rutas mantenida a mano
    (que quedaría desactualizada en cuanto se añadiera un servicio nuevo): recorre sus propios
    `sys.modules` ya importados, y si alguno vive bajo `src/` y su mtime en disco es POSTERIOR a
    cuándo arrancó este proceso, el código que este backend tiene cargado ya no coincide con el
    de disco — es genuinamente obsoleto, cubriendo automáticamente cualquier ruta/servicio que
    use (incluidos los importados perezosamente dentro de cada vista, una vez se haya servido al
    menos una petición que los cargue)."""
    try:
        for mod in list(sys.modules.values()):
            f = getattr(mod, "__file__", None)
            if not f or not f.endswith(".py"):
                continue
            try:
                f_abs = os.path.abspath(f)
                if not f_abs.startswith(_RAIZ_SRC + os.sep):
                    continue
                if os.path.getmtime(f_abs) > _INICIADO_EN:
                    return True
            except OSError:
                continue
    except Exception:
        return False
    return False


def crear_app():
    """Crea la app Flask con los endpoints de webhooks. Importa Flask aquí
    (lazy) para no exigirlo en despliegues de solo escritorio."""
    from flask import Flask, jsonify, request

    # A5.1: en producción, no arrancar sin secretos críticos (JWT + clave maestra).
    try:
        from src.seguridad.entorno import validar_arranque_seguro
        validar_arranque_seguro()
    except RuntimeError:
        raise
    except Exception as e:
        logger.debug("validar_arranque_seguro: %s", e)

    app = Flask("smart_manager_backend")

    @app.get("/salud")
    def salud():
        return jsonify({"estado": "ok", "servicio": "smart-manager-backend",
                        "iniciado_en": _INICIADO_EN,
                        "codigo_desactualizado": _codigo_propio_desactualizado()})

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

    # (El webhook de MARKETPLACE Stripe Connect se retiró con el desmontaje del pagos_marketplace/lonja.)

    # Tienda online propia (Escenario B): storefront dinámico por empresa.
    try:
        from src.backend.storefront import crear_blueprint
        app.register_blueprint(crear_blueprint())
    except Exception as e:
        logger.warning("Storefront no disponible: %s", e)

    # Smart Suppliers (Fase A): Portal Web del Proveedor (onboarding + catálogo B2B).
    try:
        from src.backend.portal_proveedor import crear_blueprint as crear_blueprint_portal_proveedor
        app.register_blueprint(crear_blueprint_portal_proveedor())
    except Exception as e:
        logger.warning("Portal proveedor no disponible: %s", e)

    # Smart Suppliers (Fase B): Extranet B2B de la Empresa (catálogo, carrito, reposición).
    try:
        from src.backend.portal_empresa_b2b import crear_blueprint as crear_blueprint_portal_empresa
        app.register_blueprint(crear_blueprint_portal_empresa())
    except Exception as e:
        logger.warning("Portal empresa B2B no disponible: %s", e)

    # Smart Suppliers (migración de las 9 pestañas): Gestión (Homologar/Devoluciones/Incidencias/
    # Evaluación/Recepciones/Facturas/Contratos/Informes/Calidad) dentro de la misma Extranet Empresa.
    try:
        from src.backend.portal_empresa_gestion import crear_blueprint as crear_blueprint_portal_gestion
        app.register_blueprint(crear_blueprint_portal_gestion())
    except Exception as e:
        logger.warning("Portal empresa Gestión no disponible: %s", e)

    # Portal del Empleado (extranet): gestión de pedidos online (Preparar/Enviar/Entregar) — sustituye
    # al diálogo Qt `gui/portal_web_home.PortalWebHome`, abierto desde "Venta almacén" del TPV.
    try:
        from src.backend.portal_empleado_web import crear_blueprint as crear_blueprint_portal_empleado
        app.register_blueprint(crear_blueprint_portal_empleado())
    except Exception as e:
        logger.warning("Portal del empleado no disponible: %s", e)

    # API REST versionada (/api/v1): Enterprise REST API (Fase III · B2, ver ADR-0001) — sustituye al
    # blueprint legacy `src.backend.api` (Fase A1, @deprecated, ver su docstring). Hasta ahora este
    # backend seguía montando el blueprint legacy porque el cambio de esta línea nunca se completó
    # tras Fase III; la app móvil y el resto de la API nueva (customers/suppliers/orders/stock/
    # notifications/agenda/tasks/incidents/workflow/documents/timeline/catalogo/...) llevaban meses
    # sin ser alcanzables por ningún servidor real.
    try:
        from src.api import crear_api
        app.register_blueprint(crear_api("v1"))
    except Exception as e:
        logger.warning("API REST no disponible: %s", e)

    # Conector MCP (Model Context Protocol) de SOMA — "SOMA — Smart Manager Copilot" — transporte
    # Streamable HTTP en `/mcp` + envoltura OAuth 2.1/DCR en `/mcp/oauth/*` (ver src/mcp_server/,
    # razonamiento de la decisión de transporte en transport.py). Mismo puerto, sin proxy.
    try:
        from src.mcp_server.oauth import crear_blueprint as crear_blueprint_mcp_oauth
        app.register_blueprint(crear_blueprint_mcp_oauth())
        from src.mcp_server.transport import crear_blueprint as crear_blueprint_mcp
        app.register_blueprint(crear_blueprint_mcp())
    except Exception as e:
        logger.warning("Conector MCP no disponible: %s", e)

    return app


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
    logger.info("Backend escuchando en %s:%s", host, port)
    crear_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
