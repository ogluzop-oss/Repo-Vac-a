"""
Integraciones Comerciales · suscriptor de `VENTA_REGISTRADA` (cierre de brecha).

Los 11 adaptadores reales de canal (WooCommerce/Shopify/Amazon/eBay/Miravia/AliExpress/TikTok Shop/
Prestashop/Magento/OpenCart + Hostinger/web_generica) tienen `exportar_stock(*, id_empresa=None,
usuario=None, articulos=None)` REAL y operativo — pero, hasta este módulo, SIN NINGÚN llamador en
producción: solo lo invocaban los tests unitarios. Cada venta debe reflejarse como stock reducido en
los canales externos que la empresa tenga conectados y con credenciales operativas, pero NUNCA de forma
SÍNCRONA dentro de la transacción de venta — una API externa lenta o caída no puede ralentizar ni romper
el checkout. Este listener por tanto SOLO ENCOLA un trabajo real por canal (reutilizando la cola local
de `cola_jobs`, Fase WEB-16.5, que el dashboard ya renderiza); `sync_worker` es quien, en segundo plano,
llama de verdad a `exportar_stock`.

Patrón de suscripción: igual que `gemelo/eventos_twin.py` (bulletproof, idempotente, vía
`src.services.eventos`) — NO es un motor de eventos nuevo, es un suscriptor más del Event Bus existente.
"""

import logging

logger = logging.getLogger("marketplace.integraciones_comerciales.sync_venta_listener")

_SUSCRITO = False


def _items_venta(venta_id, id_empresa) -> list:
    """SKUs vendidos en el ticket. Consulta directa a `venta_items` (mismo patrón que
    `db/reconciliacion.py:154`; no existe un getter compartido de "ítems de una venta" en `db/`)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT codigo_articulo FROM venta_items "
                       "WHERE venta_id=%s AND id_empresa=%s", (venta_id, id_empresa))
            out = []
            for r in cur.fetchall():
                cod = r.get("codigo_articulo") if isinstance(r, dict) else r[0]
                if cod:
                    out.append(str(cod))
            return out
    except Exception as e:
        logger.debug("_items_venta(%s): %s", venta_id, e)
        return []


def _canales_conectados(id_empresa) -> list:
    """Canales de la empresa con integración CREADA+HABILITADA y adaptador real OPERATIVO (credenciales
    presentes, misma comprobación que `_via_adaptador` en la GUI) y con capacidad `exportar_stock`.
    Reutiliza `centro`/`servicio`/`motor` existentes (N7); no resuelve credenciales por su cuenta."""
    from src.services.marketplace.integraciones_comerciales import centro, motor, servicio
    try:
        integraciones = {i["plataforma"]: i for i in (servicio.listar(id_empresa) or [])}
    except Exception:
        integraciones = {}
    out = []
    for p in (centro.plataformas_soportadas() or []):
        clave = p["clave"]
        integ = integraciones.get(clave)
        if not integ or not integ.get("habilitada", True):
            continue   # no conectado por la empresa, o deshabilitado explícitamente
        try:
            adap = motor.adaptador(clave)
        except Exception:
            continue
        if not hasattr(adap, "exportar_stock"):
            continue   # adaptador PREPARADO (sin implementación real) u otro tipo de canal
        try:
            if centro.operativo(clave, id_empresa):
                out.append(clave)
        except Exception:
            continue
    return out


def _handler(ev):
    try:
        if ev.get("tipo") != "VENTA_REGISTRADA":
            return
        id_empresa = ev.get("id_empresa")
        venta_id = ev.get("ref_id")
        if not (id_empresa and venta_id):
            return
        skus = _items_venta(venta_id, id_empresa)
        if not skus:
            return
        canales = _canales_conectados(id_empresa)
        if not canales:
            return
        from src.services.marketplace.integraciones_comerciales import cola_jobs
        articulos = [{"sku": s} for s in skus]
        usuario = ev.get("usuario")
        for clave in canales:
            cola_jobs.encolar(id_empresa, clave, "exportar_stock", articulos=articulos, usuario=usuario)
        logger.info("venta %s emp=%s: encolada exportación de stock a %s (%d sku)",
                   venta_id, id_empresa, canales, len(skus))
    except Exception as e:
        logger.debug("handler sync_venta_listener: %s", e)


def suscribir() -> bool:
    """Suscribe este listener al Event Bus (idempotente). Se llama al importar el paquete
    (`integraciones_comerciales/__init__.py`) y de nuevo al registrar el worker en el Scheduler
    (`sync_worker.registrar_jobs_sync_canales`, vía `main.py`) — mismo patrón de doble punto de entrada
    degradable que el resto del módulo."""
    global _SUSCRITO
    if _SUSCRITO:
        return True
    try:
        from src.services import eventos as EV
        EV.suscribir("VENTA_REGISTRADA", _handler)
        _SUSCRITO = True
        logger.info("sync_venta_listener suscrito a VENTA_REGISTRADA.")
        return True
    except Exception as e:
        logger.debug("suscribir sync_venta_listener: %s", e)
        return False
