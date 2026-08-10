"""
Comercio Digital · Recogida en tienda / Click & Collect (mejora funcional).

NO es un módulo nuevo ni un motor paralelo: es una MODALIDAD de cumplimiento (`PICKUP_STORE`) que
orquesta EXCLUSIVAMENTE infraestructura existente de Comercio Digital:

  · Checkout único (`checkout.confirmar(cumplimiento="PICKUP_STORE")`) — mismo flujo, distinta modalidad.
  · Availability por tienda (juez único de disponibilidad; nunca central/global/otra tienda).
  · Reservation Ledger (`reservas`: reserva ligada a la Transacción; libera/consume; nunca mueve stock).
  · Transacción Comercial única (`transacciones.transicionar`, estados reutilizados + EXPIRADA aditivo).
  · Pago y reembolso (`pagos.cobrar_express` / `pagos.refund`, provider-agnostic, sin lógica bancaria).
  · Salida física SOLO en la recogida por la POLÍTICA ÚNICA (`db.salida_stock.salida_stock_oficial`).
  · Scheduler (expiración 24 h), Event Bus (PICKUP_*), RBAC (pickup.*), Auditoría. Multiempresa/tienda.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from src.db.conexion import log_auditoria, obtener_conexion

logger = logging.getLogger("cd.pickup")

FASE = "click_collect"
CUMPLIMIENTO = "PICKUP_STORE"
RECOGIDA_TTL_HORAS = 24


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)


def _puede(usuario, permiso, emp):
    """RBAC reutilizando el motor único; degradable (ADMIN/API exentos, sin motor → no bloquea)."""
    perfil = (usuario or {}).get("perfil")
    if perfil in ("ADMINISTRADOR", "SUPERADMIN", "API"):
        return True
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario, permiso, id_empresa=emp)
    except Exception:
        return True


def _evento(tipo, id_tx, emp, payload=None):
    try:
        from src.platform import capabilities as cap
        eb = cap.eventbus()
        if eb is not None:
            eb.publish(tipo, id_empresa=emp, ref_entidad="transaccion", ref_id=id_tx,
                       payload=payload or {})
    except Exception as e:
        logger.debug("evento %s: %s", tipo, e)


def _audit(accion, id_tx, emp, id_tienda=None, motivo=None):
    try:
        log_auditoria("comercio_digital", f"PICKUP_{accion}", "transaccion_comercial",
                      f"tx={id_tx} empresa={emp} tienda={id_tienda or ''} {motivo or ''}"[:255])
    except Exception:
        pass


def _notificar(evento, emp, id_tx, estado):
    try:
        from src.services.comercio_digital import gobernanza
        gobernanza.notificar_cliente(evento, id_empresa=emp, com_id=id_tx, estado=estado)
    except Exception:
        pass


def _tx(id_tx, emp):
    from src.services.comercio_digital import transacciones
    tx = transacciones.obtener(id_tx, emp)
    if tx and isinstance(tx.get("metadata"), str):
        try:
            tx["metadata"] = json.loads(tx["metadata"])
        except Exception:
            tx["metadata"] = {}
    return tx


def _es_pickup(tx) -> bool:
    return bool(tx) and (tx.get("metadata") or {}).get("cumplimiento") == CUMPLIMIENTO


def _set_recogida_limite(id_tx, emp, horas=RECOGIDA_TTL_HORAS):
    limite = (datetime.now() + timedelta(hours=horas)).isoformat()
    tx = _tx(id_tx, emp) or {}
    meta = dict(tx.get("metadata") or {})
    meta["recogida_limite"] = limite
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transaccion_comercial SET metadata=%s WHERE id_tx=%s AND id_empresa=%s",
                        (json.dumps(meta), id_tx, emp))
            conn.commit()
    except Exception as e:
        logger.debug("set recogida_limite (%s): %s", id_tx, e)
    return limite


# ── 1) RESERVA (reutiliza el checkout único, modalidad PICKUP_STORE) ──────────
def reservar(*, id_empresa=None, id_tienda, cliente=None, lineas, moneda="EUR", canal=None,
             actor=None):
    """Crea la reserva de recogida reutilizando `checkout.confirmar` (store-only). Reduce ATP vía
    Reservation Ledger; NO mueve stock. Publica PICKUP_RESERVED. Requiere `id_tienda`."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import checkout
    res = checkout.confirmar(id_empresa=emp, id_tienda=id_tienda, cliente=cliente, lineas=lineas,
                             moneda=moneda, canal=canal, cumplimiento=CUMPLIMIENTO,
                             actor=actor or "pickup")
    if not res.get("ok"):
        return res
    id_tx = res["id_tx"]
    _evento("PICKUP_RESERVED", id_tx, emp, {"id_tienda": id_tienda, "total": res.get("total")})
    _audit("RESERVED", id_tx, emp, id_tienda)
    return {"ok": True, "id_tx": id_tx, "estado": "CONFIRMADA", "total": res.get("total"),
            "reservas": res.get("reservas")}


# ── 2) PAGO (reutiliza la pasarela existente) ─────────────────────────────────
def pagar(id_tx, *, id_empresa=None, proveedor=None, referencia=None, actor=None):
    """Cobra la reserva reutilizando el cobro en 1 clic `pagos.cobrar_express` (provider-agnostic) y fija el
    plazo de recogida (24 h). N7: NO repite `iniciar`+`confirmar` a mano — usa el orquestador único.
    Con pasarela REAL el pago queda `pendiente` (confirma por webhook) y NO se fija aún el plazo; en
    'simulado' se auto-confirma → PAGADA (comportamiento previo). `referencia` se conserva por compat."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import pagos
    r = pagos.cobrar_express(id_tx, proveedor=proveedor, id_empresa=emp, actor=actor or "pickup")
    if not r.get("ok"):
        return r
    if r.get("pendiente"):                                  # pasarela real: la confirma el webhook
        return {"ok": True, "estado": r.get("estado", "pendiente"), "pendiente": True,
                "referencia": r.get("referencia"), "url": r.get("url")}
    limite = _set_recogida_limite(id_tx, emp)
    _notificar("PickupReserved", emp, id_tx, "PAGADA")
    return {"ok": True, "estado": "PAGADA", "recogida_limite": limite}


# ── 3) PREPARACIÓN (personal de tienda; no mueve stock) ───────────────────────
def preparar(id_tx, *, id_empresa=None, usuario=None, actor=None):
    """Marca el pedido PREPARADO (estado PREPARANDO). NO mueve stock ni genera venta. RBAC pickup.preparar."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "pickup.preparar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "pickup.preparar"}
    from src.services.comercio_digital import transacciones
    res = transacciones.transicionar(id_tx, "PREPARANDO", actor=actor or "pickup", id_empresa=emp,
                                     motivo="pickup preparado")
    if res.get("ok"):
        _evento("PICKUP_PREPARED", id_tx, emp)
        _audit("PREPARED", id_tx, emp)
        _notificar("PickupPrepared", emp, id_tx, "PREPARANDO")
    return res


# ── 4) RECOGIDA (única salida física de stock: política única) ────────────────
def recoger(id_tx, *, id_empresa=None, usuario=None, actor=None):
    """Valida la entrega presencial: CONSUME las reservas y ejecuta la salida física por la POLÍTICA
    ÚNICA (`salida_stock_oficial`, la misma del TPV/envíos). Cierra la Transacción. RBAC pickup.entregar."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "pickup.entregar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "pickup.entregar"}
    from src.services.comercio_digital import transacciones
    from src.services.comercio_digital.inventario import reservas
    tx = _tx(id_tx, emp)
    if not _es_pickup(tx):
        return {"ok": False, "motivo": "no es una reserva de recogida"}
    if tx.get("estado") not in ("PAGADA", "PREPARANDO"):
        return {"ok": False, "motivo": f"estado no recogible: {tx.get('estado')}"}
    id_tienda = tx.get("id_tienda")
    consumidas = salidas = 0
    for r in reservas.activas(id_tx, emp):
        if not reservas.consumir(r["id_reserva"], actor=actor or "pickup", id_empresa=emp):
            continue
        consumidas += 1
        try:
            from src.db import salida_stock as _SS
            id_t = id_tienda if r.get("bucket") == "tienda_activa" else id_tienda
            _SS.salida_stock_oficial(r.get("codigo_articulo"), r.get("cantidad"),
                                     id_documento=id_tx, id_empresa=emp, id_tienda=id_t,
                                     contexto="comercio_digital", tipo="SALIDA_VENTA",
                                     origen="COMERCIO", usuario=actor or "pickup",
                                     observaciones=f"Recogida en tienda {id_tx}")
            salidas += 1
        except Exception as ex:
            logger.debug("salida física recogida (%s): %s", id_tx, ex)
    # ENTREGADA (recogida) → FACTURADA (finalizada). Reutiliza la máquina de estados.
    transacciones.transicionar(id_tx, "ENTREGADA", actor=actor or "pickup", id_empresa=emp,
                               motivo="pickup recogido")
    res = transacciones.transicionar(id_tx, "FACTURADA", actor=actor or "pickup", id_empresa=emp,
                                     motivo="pickup finalizado")
    _evento("PICKUP_COLLECTED", id_tx, emp, {"reservas_consumidas": consumidas, "salidas": salidas})
    _audit("COLLECTED", id_tx, emp, id_tienda)
    _notificar("PickupCollected", emp, id_tx, "ENTREGADA")
    return {"ok": bool(res.get("ok")), "estado": "FINALIZADA", "reservas_consumidas": consumidas,
            "salidas_stock": salidas}


# ── 5) CANCELACIÓN (cliente/empleado; libera reserva + reembolso) ─────────────
def cancelar(id_tx, *, id_empresa=None, usuario=None, actor=None, motivo="cancelada por el cliente"):
    """Cancela la reserva antes de la recogida: libera el Reservation Ledger, reembolsa (pasarela) y
    publica los eventos. NUNCA mueve stock físico. RBAC pickup.cancelar (o el propio cliente)."""
    emp = _emp(id_empresa)
    if usuario is not None and not _puede(usuario, "pickup.cancelar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "pickup.cancelar"}
    from src.services.comercio_digital import pagos, transacciones
    from src.services.comercio_digital.inventario import reservas
    tx = _tx(id_tx, emp)
    if not _es_pickup(tx):
        return {"ok": False, "motivo": "no es una reserva de recogida"}
    if tx.get("estado") not in ("CONFIRMADA", "PAGADA", "PREPARANDO"):
        return {"ok": False, "motivo": f"no cancelable en estado {tx.get('estado')}"}
    return _cerrar(id_tx, emp, "CANCELADA", "PICKUP_CANCELLED", "CANCELLED", motivo, actor,
                   reembolsar=(tx.get("estado") in ("PAGADA", "PREPARANDO")))


# ── 6) EXPIRACIÓN AUTOMÁTICA (Scheduler; 24 h) ────────────────────────────────
def expirar_vencidas(*, id_empresa=None, ahora=None):
    """Cancela automáticamente las reservas de recogida no recogidas en plazo (24 h): libera ledger,
    reembolsa y publica eventos. Reutiliza el Scheduler (registrar_job). Devuelve el nº expiradas."""
    from src.services.comercio_digital import transacciones
    ahora = ahora or datetime.now()
    expiradas = 0
    for estado in ("PAGADA", "PREPARANDO"):
        for tx in transacciones.listar(id_empresa=id_empresa, estado=estado, limite=1000):
            meta = tx.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if (meta or {}).get("cumplimiento") != CUMPLIMIENTO:
                continue
            limite = (meta or {}).get("recogida_limite")
            if not limite:
                continue
            try:
                venc = datetime.fromisoformat(limite)
            except Exception:
                continue
            if venc > ahora:
                continue
            emp = tx.get("id_empresa")
            _cerrar(tx["id_tx"], emp, "EXPIRADA", "PICKUP_EXPIRED", "EXPIRED",
                    "no recogida en plazo (24h)", "scheduler", reembolsar=True)
            expiradas += 1
    return {"ok": True, "expiradas": expiradas}


def _cerrar(id_tx, emp, estado_final, evento_cierre, audit_accion, motivo, actor, *, reembolsar):
    """Cierre común (cancelación/expiración): transición + liberar reservas + reembolso + eventos +
    auditoría. NUNCA mueve stock (la salida física solo ocurre en la recogida)."""
    from src.services.comercio_digital import pagos, transacciones
    from src.services.comercio_digital.inventario import reservas
    res = transacciones.transicionar(id_tx, estado_final, actor=actor, id_empresa=emp, motivo=motivo)
    liberadas = 0
    for r in reservas.activas(id_tx, emp):
        if reservas.liberar(r["id_reserva"], actor=actor, id_empresa=emp):
            liberadas += 1
    reembolso = None
    if reembolsar:
        reembolso = pagos.refund(id_tx, id_empresa=emp, actor=actor, motivo=motivo,
                                 evento="PICKUP_REFUNDED")
    _evento(evento_cierre, id_tx, emp, {"liberadas": liberadas, "reembolso": bool(reembolso)})
    _audit(audit_accion, id_tx, emp, motivo=motivo)
    _notificar(f"Pickup{audit_accion.capitalize()}", emp, id_tx, estado_final)
    return {"ok": bool(res.get("ok")), "estado": estado_final, "reservas_liberadas": liberadas,
            "reembolso": reembolso}


def registrar_job(id_empresa=None) -> bool:
    """Registra la expiración periódica en el Scheduler (capacidad, degradable/opt-in)."""
    try:
        from src.services.scheduler_enterprise import core as sch
        sch.registrar_job("comercio_pickup_expirar", lambda *_a, **_k: expirar_vencidas())
        return True
    except Exception as e:
        logger.debug("registrar_job pickup: %s", e)
        return False


def descriptor() -> dict:
    return {"servicio": "comercio_digital.pickup", "modalidad": CUMPLIMIENTO, "ttl_horas": RECOGIDA_TTL_HORAS,
            "motor_nuevo": False, "mueve_stock_fuera_de_recogida": False,
            "reutiliza": ["checkout", "availability", "reservas (Reservation Ledger)", "transacciones",
                          "pagos + refund", "salida_stock_oficial", "scheduler", "eventbus", "rbac",
                          "auditoria"],
            "estados": ["CONFIRMADA", "PAGADA", "PREPARANDO", "ENTREGADA", "FACTURADA", "CANCELADA",
                        "EXPIRADA"],
            "eventos": ["PICKUP_RESERVED", "PICKUP_PREPARED", "PICKUP_COLLECTED", "PICKUP_CANCELLED",
                        "PICKUP_EXPIRED", "PICKUP_REFUNDED"]}


__all__ = ["FASE", "CUMPLIMIENTO", "RECOGIDA_TTL_HORAS", "reservar", "pagar", "preparar", "recoger",
           "cancelar", "expirar_vencidas", "registrar_job", "descriptor"]
