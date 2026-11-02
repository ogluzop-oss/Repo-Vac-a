"""
Integraciones Comerciales · WORKER de exportación de stock (cierre de brecha: los 11 adaptadores reales
de canal — WooCommerce/Shopify/Amazon/… — tienen `exportar_stock` operativo pero, hasta ahora, SIN
NINGÚN llamador en producción; solo lo invocaban los tests unitarios).

Este módulo aporta el runner ÚNICO de la cola local (`cola_jobs`, Fase WEB-16.5): despacha por
`job["tipo"]` en vez de asumir una sola semántica, porque la cola es una FIFO COMPARTIDA entre dos
orígenes de trabajo distintos — el botón manual "Sincronizar/Reintentar" de
`gui/integraciones_comerciales_gui.py` (tipo `sincronizar`/`reintentar`) y los trabajos `exportar_stock`
que encola `sync_venta_listener` tras cada venta (`VENTA_REGISTRADA`). Antes de este módulo la GUI tenía
su propio runner interno que solo sabía tratar `sincronizar`; al compartir la cola con un segundo tipo de
trabajo, ese runner ejecutaría la acción equivocada sobre un trabajo que no es el suyo. Centralizar aquí
(en `services`, no en la GUI, conforme a CLAUDE.md) corrige eso — lo usan AMBOS llamadores.

El drenado PERIÓDICO (para que un trabajo encolado no se quede en `pendiente` para siempre) lo dispara
`main.py` con un QTimer corto que llama a `scheduler.ejecutar_job("ic_sync_canales")` DIRECTAMENTE — el
mismo patrón que ya usa `soma/observador.SomaObserver._tick_scheduler` (late de ~90 s) para activar
`scheduler.ejecutar_job("soma_observacion")` sin esperar a la granularidad de HORAS de
`scheduler.ejecutar_pendientes()`/`scheduler_jobs.intervalo_horas` (columna `INT`). El job también se
registra en el Scheduler (`registrar_jobs_sync_canales`, mismo patrón exacto que
`compras/b2b_rappels.registrar_jobs_rappels`) para quedar auditado/visible en el panel de jobs del ERP,
con `intervalo_horas=1` (la granularidad mínima que admite la columna — igual que
`resiliencia_sync`/`resiliencia_watchdog`/`sat_email_ticket`/`distribucion_reintentos`/`b2b_rfq_cierre`,
los jobs más frecuentes ya existentes en este catálogo).
"""

import logging

logger = logging.getLogger("marketplace.integraciones_comerciales.sync_worker")


def _disponible(adap, id_empresa) -> bool:
    try:
        return bool(adap.disponible(id_empresa))
    except TypeError:
        try:
            return bool(adap.disponible())
        except Exception:
            return False
    except Exception:
        return False


def _audit(plataforma, ok, detalle):
    """Auditoría GENÉRICA (una sola, por plataforma) del resultado de un trabajo de la cola. Aditiva a la
    auditoría propia de cada adaptador (p.ej. `woocommerce.auditoria.WOO_EXPORT`): usa nombres de acción
    que `centro._conteo_eventos` ya reconoce por subcadena (`SYNC_FINISH`/`ERROR`) para CUALQUIER
    plataforma, de modo que el panel de estadísticas de la GUI muestre sincronizaciones/errores reales
    también para `exportar_stock` sin tener que tocar los 11 módulos de auditoría por adaptador."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", "IC_SYNC_FINISH" if ok else "IC_SYNC_ERROR", plataforma,
                      (detalle or "")[:240])
    except Exception:
        pass


def ejecutar_trabajo(job, *, usuario=None) -> tuple:
    """Runner ÚNICO de la cola local de Integraciones Comerciales. Devuelve `(ok, resultado)`.

    - `tipo="exportar_stock"` (encolado por `sync_venta_listener`): llama de verdad a
      `adaptador.exportar_stock(...)` si el canal está operativo (credenciales reales); si no, falla
      HONESTAMENTE (nunca marca el trabajo como completado sin haber llamado al adaptador real).
    - `tipo="sincronizar"/"reintentar"` (encolado por la GUI): MISMA resolución que tenía el runner
      inline de `_encolar_y_ejecutar` (adaptador real vía `sincronizacion_inicial`, o estado simulado
      del servicio si no hay adaptador operativo) — solo que ahora centralizada aquí.
    """
    from src.services.marketplace.integraciones_comerciales import motor, servicio
    plataforma = job.get("plataforma")
    id_empresa = job.get("id_empresa")
    tipo = job.get("tipo") or "sincronizar"
    usr = job.get("usuario") or usuario
    try:
        adap = motor.adaptador(plataforma)
    except Exception as e:
        return False, {"error": str(e)}
    op = _disponible(adap, id_empresa)

    if tipo == "exportar_stock":
        if not (op and hasattr(adap, "exportar_stock")):
            r = {"ok": False, "codigo": "MISSING_CREDENTIALS",
                "error": "canal sin credenciales operativas (o sin soporte de exportación de stock)"}
            _audit(plataforma, False, f"exportar_stock emp={id_empresa}: {r['error']}")
            return False, r
        try:
            r = adap.exportar_stock(id_empresa=id_empresa, usuario=usr, articulos=job.get("articulos") or [])
            ok = bool(isinstance(r, dict) and r.get("ok"))
        except Exception as e:
            logger.error("exportar_stock %s emp=%s: %s", plataforma, id_empresa, e)
            ok, r = False, {"ok": False, "error": str(e)}
        _audit(plataforma, ok, f"exportar_stock emp={id_empresa} resultado={r}")
        return ok, r

    # tipo sincronizar/reintentar.
    r = None
    if op and hasattr(adap, "sincronizacion_inicial"):
        try:
            r = adap.sincronizacion_inicial(id_empresa=id_empresa, usuario=usr)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
    if r is None:
        try:
            r = servicio.sincronizar(id_empresa, plataforma, usuario=usr)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
    ok = bool(isinstance(r, dict) and r.get("ok", True) and r.get("codigo") is None)
    return ok, r


def drenar_exportaciones(id_empresa=None) -> str:
    """Job del Scheduler: ejecuta TODOS los trabajos PENDIENTES de la cola local (exportaciones tras
    venta + sincronizaciones manuales no recogidas por la GUI). Devuelve un resumen textual para el
    historial del Scheduler (`scheduler_historial`)."""
    from src.services.marketplace.integraciones_comerciales import cola_jobs
    hechos = cola_jobs.ejecutar_pendientes(lambda job: ejecutar_trabajo(job))
    if not hechos:
        return "sin trabajos pendientes"
    ok = sum(1 for j in hechos if j["estado"] == "completado")
    return f"trabajos procesados={len(hechos)} ok={ok} fallidos={len(hechos) - ok}"


def registrar_jobs_sync_canales(id_empresa=None):
    """Registra el worker en el Scheduler (idempotente), mismo patrón exacto que
    `compras.b2b_rappels.registrar_jobs_rappels`. Degradable: si el Scheduler no está disponible, la
    cola sigue pudiendo drenarse manualmente (botón de la GUI)."""
    try:
        from src.services import scheduler
        scheduler.registrar("ic_sync_canales", drenar_exportaciones)
        scheduler.registrar_job("ic_sync_canales", intervalo_horas=1,
                                descripcion="Integraciones comerciales: exportar stock a canales "
                                           "externos conectados tras cada venta (cola local)",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_sync_canales: %s", e)
