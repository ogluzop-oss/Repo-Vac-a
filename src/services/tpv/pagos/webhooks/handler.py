"""
Núcleo de procesamiento de WEBHOOKS de pago (Fase 3).

`procesar_webhook` es independiente del transporte (lo llama el endpoint Flask,
pero es 100% testeable sin servidor). Flujo profesional:

  1. valida firma/autenticidad (verificador por proveedor, registro extensible),
  2. protege de replay/duplicados (idempotencia por evento, tabla pagos_webhooks_log),
  3. localiza el pedido (por referencia_pago / referencia_externa / id),
  4. registra la transacción y actualiza el estado del pedido (→ PAGADO dispara la
     cadena: justificante + stock + aviso al cliente),
  5. registra auditoría.

Devuelve {ok, http, id_pedido, estado, duplicado, mensaje}. Los secretos salen
siempre de la config por empresa (`pasarela_config`), nunca del código.
"""

import hashlib
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("pagos.webhooks.handler")


def _localizar_pedido(referencia, id_empresa):
    """id_pedido de un pedido online cuya referencia de pago/externa coincida."""
    if not referencia:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id_pedido, estado FROM pedidos_online "
                "WHERE id_empresa=%s AND (referencia_pago=%s OR referencia_externa=%s "
                "OR id_pedido=%s) LIMIT 1",
                (id_empresa, referencia, referencia, referencia))
            r = cur.fetchone()
            if not r:
                return None
            return (r[0], r[1]) if not isinstance(r, dict) else (r["id_pedido"], r["estado"])
    except Exception as e:
        logger.error("_localizar_pedido(%s): %s", referencia, e)
        return None


def _set_estado_pago(id_pedido, estado_pago):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET estado_pago=%s WHERE id_pedido=%s",
                        (estado_pago, id_pedido))
            conn.commit()
    except Exception as e:
        logger.debug("_set_estado_pago(%s): %s", id_pedido, e)


def _auditar(usuario_emp, accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("webhook", accion, "pagos_webhooks_log", detalle)
    except Exception as e:
        logger.debug("auditar webhook: %s", e)


def procesar_webhook(proveedor, headers, body, id_empresa=None, ip_origen=None) -> dict:
    id_empresa = id_empresa or EMPRESA_DEFAULT_ID
    from src.db import pagos as pagos_db
    from src.db import pagos_webhooks as wlog
    from src.services.tpv.pagos.webhooks.registry import verificador_de

    verificador = verificador_de(proveedor)
    if verificador is None:
        return {"ok": False, "http": 400, "mensaje": f"Proveedor '{proveedor}' no soportado."}

    config = pagos_db.obtener_config(id_empresa)
    res = verificador.verificar(headers or {}, body or b"", config)
    if not res.get("ok"):
        _auditar(id_empresa, "WEBHOOK_RECHAZADO", f"{proveedor}: {res.get('mensaje')}")
        logger.warning("Webhook %s rechazado (empresa %s): %s", proveedor, id_empresa, res.get("mensaje"))
        return {"ok": False, "http": 400, "mensaje": res.get("mensaje", "Firma no válida.")}

    # Idempotencia: evento_id obligatorio; si falta, derivar uno estable.
    evento_id = res.get("evento_id")
    if not evento_id:
        base = f"{res.get('referencia')}|{res.get('estado')}|{res.get('evento_tipo')}"
        evento_id = "auto-" + hashlib.sha256(base.encode()).hexdigest()[:32]

    id_log = wlog.reclamar_evento(proveedor, evento_id, evento_tipo=res.get("evento_tipo"),
                                  referencia=res.get("referencia"), ip_origen=ip_origen,
                                  id_empresa=id_empresa)
    if id_log is None:
        # Ya procesado: respondemos 200 para que la plataforma deje de reintentar.
        return {"ok": True, "http": 200, "duplicado": True, "mensaje": "Evento duplicado (ignorado)."}

    referencia = res.get("referencia")
    estado_evt = res.get("estado")          # pagado | fallido | pendiente
    encontrado = _localizar_pedido(referencia, id_empresa)
    if not encontrado:
        wlog.actualizar_evento(id_log, estado=estado_evt, resultado="sin_pedido",
                               evento_tipo=res.get("evento_tipo"))
        _auditar(id_empresa, "WEBHOOK_SIN_PEDIDO", f"{proveedor}:{referencia}")
        return {"ok": True, "http": 200, "id_pedido": None, "estado": estado_evt,
                "duplicado": False, "mensaje": "Recibido; sin pedido asociado."}

    id_pedido, estado_pedido = encontrado
    estado_pago = "pagado" if estado_evt == "pagado" else "fallido" if estado_evt == "fallido" else "pendiente"
    _set_estado_pago(id_pedido, estado_pago)

    if estado_evt == "pagado" and estado_pedido != "PAGADO":
        try:
            from src.services.tpv import online_orders_service as OS
            OS.cambiar_estado(id_pedido, "PAGADO")   # dispara justificante + stock + aviso
        except Exception as e:
            logger.error("Webhook: cambiar_estado PAGADO (%s): %s", id_pedido, e)

    wlog.actualizar_evento(id_log, id_pedido=id_pedido, estado=estado_evt,
                           resultado="procesado", evento_tipo=res.get("evento_tipo"))
    _auditar(id_empresa, "WEBHOOK_PROCESADO",
             f"{proveedor}:{evento_id} pedido={id_pedido} estado={estado_evt}")
    return {"ok": True, "http": 200, "id_pedido": id_pedido, "estado": estado_evt,
            "duplicado": False, "mensaje": "Procesado."}
