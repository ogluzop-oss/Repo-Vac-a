"""
PCD · Checkout (Etapa B · Fase B5). Punto de CONVERGENCIA: todo el ecosistema desemboca aquí.

Orquesta —sin crear motores ni tablas nuevas— la reutilización de:
  Gestión Comercial (cotizar) → Availability (ATP) → Fulfillment (Plan de Cumplimiento) →
  Reservation Ledger (reserva ligada a la Transacción) → Transacción Comercial (núcleo omnicanal).

Garantías: NO mueve stock (política única), NO cobra (los pagos llegan en su fase; aquí se deja la
Transacción CONFIRMADA con reserva). Toda decisión queda en el `decision log` (Audit Replay, N9).
Multiempresa/multitienda. Degradable.
"""

from __future__ import annotations

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID

logger = logging.getLogger("cd.checkout")

FASE = "B5"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _memo_resolver(inventario, estrategia, emp, id_tienda):
    """Devuelve un `resolver(codigo, cantidad)` con CACHÉ por (codigo, cantidad) para una sola
    operación de checkout (optimización N+1 C0.P2): evita recomputar el Plan de Cumplimiento para
    líneas repetidas. Mismo resultado que llamar a `inventario.resolver` directamente."""
    _cache = {}

    def _resolver(codigo, cantidad):
        clave = (codigo, int(cantidad or 1))
        if clave not in _cache:
            _cache[clave] = inventario.resolver(codigo, cantidad, estrategia=estrategia,
                                                id_empresa=emp, id_tienda=id_tienda)
        return _cache[clave]

    return _resolver


def _sourcing(plan):
    """Sourcing de una línea a partir del Plan de Cumplimiento (asignaciones multi-origen)."""
    try:
        return {"origen": plan.origen_elegido, "asignaciones": list(plan.asignaciones),
                "cubre": plan.cubre, "estrategia": plan.estrategia}
    except Exception:
        return None


def preparar(*, id_empresa=None, lineas, cliente=None, cupon=None, lista=None, moneda="EUR",
             id_tienda=None, segmento=None, estrategia="equilibrado"):
    """VISTA PREVIA (sin efectos): cotización comercial + disponibilidad/plan por línea. No reserva,
    no crea Transacción. Es el resumen de convergencia que ve el cliente antes de confirmar."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import comercial, inventario
    coti = comercial.cotizar(lineas, cliente_id=(cliente or {}).get("id"), segmento=segmento,
                             id_tienda=id_tienda, cupon=cupon, lista=lista, moneda=moneda,
                             id_empresa=emp)
    resolver = _memo_resolver(inventario, estrategia, emp, id_tienda)   # C0.P2: caché por línea
    disponibilidad, disponible_todo = {}, True
    for l in coti["lineas"]:
        plan = resolver(l["codigo"], l["cantidad"])
        disponibilidad[l["codigo"]] = {"cubre": plan.cubre, "origen": plan.origen_elegido}
        disponible_todo = disponible_todo and plan.cubre
    return {"ok": True, "cotizacion": coti, "disponibilidad": disponibilidad,
            "disponible": disponible_todo, "total": coti["total"], "moneda": moneda}


def confirmar(*, id_empresa=None, origen="web", cliente=None, lineas, cupon=None, lista=None,
              moneda="EUR", id_tienda=None, segmento=None, canal=None, estrategia="equilibrado",
              tipo_reserva="hard", cumplimiento="DELIVERY", idempotencia_key=None, actor=None):
    """CONFIRMA el checkout: cotiza → verifica disponibilidad y planifica cumplimiento → crea la
    Transacción Comercial (CONFIRMADA) → reserva (ligada a la Transacción) → registra la decisión.
    NO cobra ni mueve stock. Devuelve {ok, id_tx, total, reservas, cotizacion}.

    `cumplimiento` es una MODALIDAD de cumplimiento (mismo checkout, no uno paralelo): `DELIVERY`
    (entrega a domicilio, por defecto) o `PICKUP_STORE` (recogida en tienda, Click & Collect). En
    PICKUP_STORE la disponibilidad se limita ESTRICTAMENTE a la tienda seleccionada (nunca central,
    global u otra tienda)."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import comercial, inventario, transacciones
    from src.services.comercio_digital.inventario import reservas

    # 1) Cotización comercial (precios de lista + promociones + cupón).
    coti = comercial.cotizar(lineas, cliente_id=(cliente or {}).get("id"), segmento=segmento,
                             id_tienda=id_tienda, cupon=cupon, lista=lista, moneda=moneda,
                             id_empresa=emp)

    # 2) Availability + Fulfillment por línea (no se puede confirmar lo que no hay).
    resolver = _memo_resolver(inventario, estrategia, emp, id_tienda)   # C0.P2: caché por línea
    planes = {}
    for l in coti["lineas"]:
        plan = resolver(l["codigo"], l["cantidad"])
        planes[l["codigo"]] = plan
        if not plan.cubre:
            return {"ok": False, "motivo": "sin disponibilidad", "codigo": l["codigo"],
                    "cotizacion": coti}

    # 2-bis) Click & Collect: la disponibilidad se limita ESTRICTAMENTE a la tienda seleccionada
    #        (Availability sigue siendo el único juez; nunca central/global/otra tienda).
    if cumplimiento == "PICKUP_STORE":
        if id_tienda is None:
            return {"ok": False, "motivo": "recogida en tienda requiere id_tienda", "cotizacion": coti}
        from src.services.comercio_digital.inventario import availability
        for l in coti["lineas"]:
            disp = availability.consultar_disponibilidad(l["codigo"], id_empresa=emp,
                                                         id_tienda=id_tienda)
            if int(disp.get("tienda", 0)) < int(l["cantidad"]):
                return {"ok": False, "motivo": "no disponible en la tienda", "codigo": l["codigo"],
                        "cotizacion": coti}

    # 3) Transacción Comercial (núcleo omnicanal) en estado CONFIRMADA.
    lineas_tx = [{"codigo": l["codigo"], "cantidad": l["cantidad"],
                  "precio_unitario": l["precio_unitario"], "subtotal": l["neto"],
                  "sourcing": _sourcing(planes[l["codigo"]])} for l in coti["lineas"]]
    id_tx = transacciones.crear(
        tipo="pedido", origen=origen, estado="CONFIRMADA", id_empresa=emp, id_tienda=id_tienda,
        cliente=cliente or {}, lineas=lineas_tx, moneda=moneda, idempotencia_key=idempotencia_key,
        metadata={"total_cotizado": coti["total"], "descuento_total": coti["descuento_total"],
                  "cupon": coti["cupon"], "canal": canal or origen, "cumplimiento": cumplimiento})
    if not id_tx:
        return {"ok": False, "motivo": "no se pudo crear la transacción", "cotizacion": coti}

    # 4) Reservas (única reducción del ATP), ligadas a la Transacción.
    reservas_creadas = []
    for codigo, plan in planes.items():
        reservas_creadas += reservas.reservar_desde_plan(id_tx, plan, tipo=tipo_reserva,
                                                         id_empresa=emp, actor=actor or "checkout",
                                                         canal=canal or origen)

    # 5) Decisión → Audit Replay (N9).
    try:
        transacciones.registrar_decision(
            id_tx, motor="checkout", decision="checkout confirmado",
            resultado={"cotizacion": coti, "reservas": reservas_creadas,
                       "planes": {k: v.as_dict() for k, v in planes.items()}},
            actor=actor or "checkout", id_empresa=emp)
    except Exception as e:
        logger.debug("decision log checkout (%s): %s", id_tx, e)

    return {"ok": True, "id_tx": id_tx, "estado": "CONFIRMADA", "total": coti["total"],
            "moneda": moneda, "reservas": reservas_creadas, "cotizacion": coti}


def cancelar(id_tx, *, id_empresa=None, actor=None) -> dict:
    """Cancela un checkout: libera las reservas activas y pasa la Transacción a CANCELADA."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import transacciones
    from src.services.comercio_digital.inventario import reservas
    liberadas = 0
    for r in reservas.activas(id_tx, emp):
        if reservas.liberar(r["id_reserva"], actor=actor or "checkout", id_empresa=emp):
            liberadas += 1
    res = transacciones.transicionar(id_tx, "CANCELADA", actor=actor or "checkout", id_empresa=emp)
    return {"ok": bool(res.get("ok")), "id_tx": id_tx, "reservas_liberadas": liberadas,
            "estado": res.get("hasta") if res.get("ok") else None}


def descriptor() -> dict:
    return {"servicio": "cd_checkout", "etapa": "B", "fase": FASE, "estado": "implementado",
            "orquesta": ["comercial", "availability", "fulfillment", "reservas", "transacciones"],
            "mueve_stock": False, "cobra": False, "crea_motor_nuevo": False, "audit_replay": True}


__all__ = ["FASE", "preparar", "confirmar", "cancelar", "descriptor"]
