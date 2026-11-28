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
    # Sesión de navegador del sitio oficial (`sitio_oficial.py`, cookie firmada de Flask para el
    # login web de clientes): reutiliza el secreto de producción YA exigido por
    # `validar_arranque_seguro()` en vez de inventar uno nuevo — un secreto más que rotar.
    app.secret_key = os.environ.get("SMART_MANAGER_JWT_SECRET", "dev-secret-no-usar-en-produccion")

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

    # Webhook de eventos de Stripe CONNECT (petición explícita, 2026-11-16) — restaura, sobre las
    # tablas NUEVAS (`suministradores`/`b2b_escrow`, no la `lonja` retirada), lo que el comentario
    # de arriba decía que se había desmontado. Distinto del webhook de facturación SaaS
    # (`backend_central/rutas_stripe.py`, STRIPE_WEBHOOK_SECRET_SAAS): Stripe exige un endpoint y un
    # secreto de firma por CADA tipo de eventos que se suscriban por separado.
    @app.post("/webhooks/stripe/connect")
    def webhook_stripe_connect():
        """Mantiene al día la caché local `suministradores.stripe_verificado` (requisito
        obligatorio para publicar catálogo/recibir pedidos, ver `b2b_catalogo`/`b2b_pedidos`) SIN
        depender de que el proveedor vuelva a abrir su panel — p. ej. si Stripe pide un documento
        adicional DESPUÉS del alta, o restringe la cuenta más tarde. Evento `account.updated`."""
        from src.services.tpv.pagos.webhooks.stripe import verificar_firma_stripe
        secreto = os.environ.get("STRIPE_WEBHOOK_SECRET_CONNECT")
        cuerpo = request.get_data() or b""
        cabeceras = dict(request.headers)
        ok, ev = verificar_firma_stripe(cabeceras, cuerpo, secreto or "")
        if not ok:
            logger.warning("Webhook Stripe Connect rechazado: %s", ev)
            return jsonify({"ok": False, "error": ev}), 400

        evento_id = ev.get("id")
        tipo = ev.get("type") or ""
        obj = (ev.get("data") or {}).get("object") or {}
        account_id = obj.get("id")

        from src.db.pagos_webhooks import reclamar_evento
        id_log = reclamar_evento("stripe_connect", evento_id, tipo, account_id, request.remote_addr)
        if id_log is None:
            # Duplicado/replay (Stripe reintenta si no respondemos 200 a tiempo): se acepta sin
            # reprocesar, para que Stripe deje de reintentar.
            return jsonify({"ok": True, "duplicado": True})

        if tipo != "account.updated" or not account_id:
            return jsonify({"ok": True, "accion": "ignorado"})

        from src.services.compras import suministradores as SUP
        payouts_enabled = bool(obj.get("payouts_enabled"))
        actualizado = SUP.actualizar_verificacion_por_cuenta(account_id, payouts_enabled)
        logger.info("Webhook Stripe Connect: account.updated %s payouts_enabled=%s actualizado=%s",
                   account_id, payouts_enabled, actualizado)
        return jsonify({"ok": True, "accion": "actualizado" if actualizado else "cuenta_no_encontrada"})

    # Sitio oficial y comercial (dominio raíz, smartmanager-app.com): presentación del ERP, planes,
    # alta/pago (Stripe Checkout) y descarga de la app — ver docstring del módulo.
    try:
        from src.backend.sitio_oficial import crear_blueprint as crear_blueprint_sitio_oficial
        app.register_blueprint(crear_blueprint_sitio_oficial())
    except Exception as e:
        logger.warning("Sitio oficial no disponible: %s", e)

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

    # Tareas periódicas del Portal B2B (onboarding comercial) — disparadas por un cron externo del
    # VPS vía secreto compartido, ver `rutas_jobs_b2b`.
    try:
        from src.backend.rutas_jobs_b2b import crear_blueprint as crear_blueprint_jobs_b2b
        app.register_blueprint(crear_blueprint_jobs_b2b())
    except Exception as e:
        logger.warning("Jobs B2B no disponibles: %s", e)

    # Buzón de sugerencias/incidencias del escritorio hacia Smart Manager (ver rutas_soporte.py).
    try:
        from src.backend.rutas_soporte import crear_blueprint as crear_blueprint_soporte
        app.register_blueprint(crear_blueprint_soporte())
    except Exception as e:
        logger.warning("Buzón de soporte no disponible: %s", e)

    # Pedidos Online (extranet): gestión de pedidos online (Preparar/Enviar/Entregar) — sustituye
    # al diálogo Qt `gui/portal_web_home.PortalWebHome`, abierto desde "Venta online" del TPV.
    try:
        from src.backend.portal_pedidos_online import crear_blueprint as crear_blueprint_portal_empleado
        app.register_blueprint(crear_blueprint_portal_empleado())
    except Exception as e:
        logger.warning("Portal Pedidos Online no disponible: %s", e)

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

    # Hosting automático del Canal Web (petición explícita, 2026-11-24): antes, CADA dominio de
    # tienda nuevo exigía duplicar a mano un bloque en el Caddyfile del VPS apuntando a
    # `/tienda/<id_empresa>` fijo (confirmado: `tienda.smartmanager-app.com` estaba codificado a
    # `id_empresa=1`, ninguna otra empresa podía tener su web publicada sin ese paso manual). Este
    # middleware WSGI resuelve el `id_empresa` dueño del Host ANTES de que Flask enrute (único
    # punto posible para reescribir el path: el `before_request` de un blueprint ya corre DESPUÉS
    # del routing, demasiado tarde) contra `cd_canal_dominios` (mismo dato que ya usa el resto del
    # Canal Web, vía `resolver_id_empresa_por_host` — sin tabla/motor nuevo) y antepone
    # `/tienda/<id_empresa>` al path real — así CUALQUIER subdominio generado por
    # `generar_subdominio`/dominio propio asignado queda servido por el storefront existente sin
    # tocar el Caddyfile ni este backend por cada empresa nueva. Degradable: cualquier fallo deja
    # la petición intacta (nunca rompe el resto de la app por un error aquí).
    _wsgi_original = app.wsgi_app

    def _wsgi_dominio_tienda(environ, start_response):
        try:
            path = environ.get("PATH_INFO", "") or "/"
            if not path.startswith(("/tienda/", "/api/", "/central", "/mcp")):
                host = environ.get("HTTP_HOST", "")
                from src.services.comercio_digital.canal_web import gestion_dominios as _GD
                id_empresa = _GD.resolver_id_empresa_por_host(host)
                if id_empresa:
                    # La home real está registrada SIN barra final ("/tienda/<id_empresa>", sin
                    # trailing slash) — anteponer el prefijo a "/" tal cual daría
                    # "/tienda/<id>/" y un 404 por el strict_slashes de Flask/Werkzeug.
                    environ["PATH_INFO"] = f"/tienda/{id_empresa}" + ("" if path == "/" else path)
        except Exception as e:
            logger.debug("middleware dominio tienda: %s", e)
        return _wsgi_original(environ, start_response)

    app.wsgi_app = _wsgi_dominio_tienda

    return app


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
    logger.info("Backend escuchando en %s:%s", host, port)
    crear_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
