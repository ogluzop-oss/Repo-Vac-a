"""
Facturación automática SaaS (cierre end-to-end). Dispara el ciclo de facturación de las suscripciones VENCIDAS
(proximo_cobro ≤ hoy) reutilizando `suscripciones.renovar` (que emite `facturas_saas`, cobra por el
`BillingProvider` y actualiza el próximo cobro). N7: no crea motor de cobro/facturación paralelo. Idempotente:
`renovar` empuja `proximo_cobro` al futuro, así que una segunda pasada el mismo día NO vuelve a facturar.
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion
from src.services.saas import suscripciones as _S

logger = logging.getLogger("saas.facturacion_automatica")

# Solo se factura automáticamente lo que está vivo y en ciclo de cobro.
_ESTADOS_FACTURABLES = ("activa", "prueba")


def suscripciones_vencidas(hoy=None) -> list:
    """Empresas cuya suscripción está vencida (proximo_cobro ≤ hoy) y en estado facturable."""
    hoy = hoy or _dt.date.today()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(_ESTADOS_FACTURABLES))
            cur.execute(f"SELECT DISTINCT id_empresa FROM suscripciones WHERE proximo_cobro<=%s AND "
                        f"estado IN ({ph})", (hoy, *_ESTADOS_FACTURABLES))
            return [r[0] if not isinstance(r, dict) else r["id_empresa"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("suscripciones_vencidas: %s", e)
        return []


def facturar_vencidas(hoy=None) -> dict:
    """Factura/renueva todas las suscripciones vencidas. Devuelve {procesadas, ok, fallidas}."""
    empresas = suscripciones_vencidas(hoy)
    procesadas = ok = fallidas = 0
    for emp in empresas:
        try:
            r = _S.renovar(emp)
            procesadas += 1
            if r.get("ok"):
                ok += 1
            else:
                fallidas += 1
        except Exception as e:
            logger.debug("facturar_vencidas(%s): %s", emp, e)
            fallidas += 1
    if procesadas:
        logger.info("Facturación automática SaaS: %s procesadas, %s ok, %s fallidas.", procesadas, ok, fallidas)
    return {"procesadas": procesadas, "ok": ok, "fallidas": fallidas}


def job(id_empresa=None) -> str:
    """Callable para el Scheduler (opt-in; solo instalaciones SaaS). Factura las vencidas."""
    r = facturar_vencidas()
    return f"saas facturación: procesadas={r['procesadas']} ok={r['ok']} fallidas={r['fallidas']}"
