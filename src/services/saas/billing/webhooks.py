"""
Webhooks de billing (FASE P0.4): sincronizan el estado de pago del proveedor con la licencia.

procesar_evento(tipo, datos) traduce eventos del proveedor (p.ej. Stripe invoice.paid /
invoice.payment_failed / customer.subscription.deleted) en cambios de factura/pago/suscripción
y licencia. Idempotente por ref_externa. Sin dependencias de red (recibe el payload ya parseado).
"""

import logging
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.saas import suscripciones as _S, licensing as _L

logger = logging.getLogger("saas.billing.webhooks")

# Mapa de eventos genéricos → acción interna.
_PAGADO = {"invoice.paid", "invoice.payment_succeeded", "payment_intent.succeeded", "pago_ok"}
_FALLIDO = {"invoice.payment_failed", "payment_intent.payment_failed", "pago_fallido"}
_CANCELADO = {"customer.subscription.deleted", "suscripcion_cancelada"}


def procesar_evento(tipo, datos=None) -> dict:
    """Sincroniza un evento de billing con la licencia. datos: {id_empresa, ref_externa, importe}."""
    datos = datos or {}
    id_empresa = datos.get("id_empresa") or EMPRESA_DEFAULT_ID
    ref = datos.get("ref_externa")
    if tipo in _PAGADO:
        _marcar_pago(id_empresa, ref, "pagado")
        _S._set_estado(id_empresa, "activa", "activa", "PAGO_RECIBIDO")
        _audit("PAGO_RECIBIDO", id_empresa, f"webhook {tipo} ref={ref}")
        return {"ok": True, "accion": "activada"}
    if tipo in _FALLIDO:
        _marcar_pago(id_empresa, ref, "fallido")
        _S._set_estado(id_empresa, "suspendida", "suspendida", "PAGO_FALLIDO")
        _audit("PAGO_FALLIDO", id_empresa, f"webhook {tipo} ref={ref}")
        return {"ok": True, "accion": "suspendida"}
    if tipo in _CANCELADO:
        _S.cancelar(id_empresa)
        _audit("EMPRESA_BLOQUEADA", id_empresa, f"webhook {tipo}")
        return {"ok": True, "accion": "cancelada"}
    return {"ok": False, "accion": "ignorado", "tipo": tipo}


def _marcar_pago(id_empresa, ref, estado):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pagos_saas SET estado=%s WHERE id_empresa=%s AND ref_externa=%s",
                        (estado, id_empresa, ref))
            conn.commit()
    except Exception as e:
        logger.debug("_marcar_pago: %s", e)


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "pagos_saas", f"{id_empresa}: {detalle}")
    except Exception:
        pass
