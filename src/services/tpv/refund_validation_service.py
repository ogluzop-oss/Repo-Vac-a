"""
Refund Validation Service — Smart Manager AI TPV Enterprise
Centralizes ALL refund eligibility rules so they can be reused by both
the manned TPV and the self-checkout, and tested in isolation.

Thin layer over refund_service: deadline, authorization and payment-method
enforcement live here as pure functions; refund_service performs the writes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.services.tpv import refund_service as _rs

logger = logging.getLogger("tpv.refund_val")


# Re-export the building blocks from refund_service so callers can import
# everything refund-validation related from one place.
buscar_venta            = _rs.buscar_venta
validar_plazo           = _rs.validar_plazo
verificar_autorizacion  = _rs.verificar_autorizacion
metodo_reembolso_permitido = _rs.metodo_reembolso_permitido


def evaluar_ticket(venta_id: int) -> dict:
    """
    Full eligibility evaluation for a ticket.
    Returns a structured dict the UI can render directly:
      {
        "existe": bool,
        "venta": dict | None,
        "dentro_plazo": bool,
        "dias_transcurridos": int,
        "plazo_maximo": int,
        "fecha_limite": str,
        "requiere_autorizacion": bool,
        "mensaje": str,
      }
    """
    venta = buscar_venta(venta_id)
    if not venta:
        return {
            "existe": False,
            "venta": None,
            "mensaje": f"No se ha encontrado el ticket #{venta_id}.",
        }

    fecha = venta["fecha"]
    if isinstance(fecha, str):
        try:
            fecha = datetime.fromisoformat(fecha)
        except ValueError:
            fecha = datetime.now()

    dentro, dias, plazo = validar_plazo(fecha)

    from datetime import timedelta
    fecha_limite = (fecha + timedelta(days=plazo)).strftime("%d/%m/%Y")

    if dentro:
        msg = "Ticket dentro del plazo de devolución."
    else:
        msg = (
            f"El ticket ha superado el plazo máximo permitido para devoluciones "
            f"({plazo} días). Han transcurrido {dias} días."
        )

    return {
        "existe": True,
        "venta": venta,
        "dentro_plazo": dentro,
        "dias_transcurridos": dias,
        "plazo_maximo": plazo,
        "fecha_limite": fecha_limite,
        "requiere_autorizacion": not dentro,
        "mensaje": msg,
    }


def validar_linea_devolucion(item: dict, cantidad_solicitada: float) -> tuple[bool, str]:
    """Validates that the requested return quantity does not exceed sold."""
    if cantidad_solicitada <= 0:
        return False, "La cantidad a devolver debe ser mayor que cero."
    vendida = float(item.get("cantidad", 0))
    if cantidad_solicitada > vendida:
        return False, (
            f"No se pueden devolver {cantidad_solicitada} unidades; "
            f"sólo se vendieron {vendida}."
        )
    return True, ""
