"""
PCD · Inventario Global Inteligente (CD-005) — SCAFFOLDING (Fase 1). Agrupa los dos motores
INDEPENDIENTES (Availability, Fulfillment) y las Reservas. Frontera inviolable: Dominio → Availability
→ Fulfillment → Workflow → política única de salida de stock. Ningún motor mueve stock.
"""

from src.services.comercio_digital.inventario import availability, fulfillment, reservas  # noqa: F401


def resolver(codigo, cantidad=1, *, estrategia=None, id_empresa=None, id_tienda="auto",
             contexto=None):
    """COMPOSICIÓN (orquestación): obtiene el mapa de Availability y se lo pasa a Fulfillment para
    obtener el Plan de Cumplimiento. Es el ÚNICO punto donde se combinan ambos motores; ninguno de
    los dos importa al otro (independencia CD-005). Devuelve un `PlanCumplimiento` inmutable."""
    disp = availability.disponibilidad(codigo, cantidad, id_empresa=id_empresa, id_tienda=id_tienda)
    return fulfillment.planificar(disp, estrategia=estrategia, contexto=contexto,
                                  id_empresa=id_empresa)


def descriptor() -> dict:
    return {"servicio": "cd_inventario", "rfc": "CD-005", "estado": "en_progreso",
            "motores": {"availability": availability.descriptor(),
                        "fulfillment": fulfillment.descriptor(),
                        "reservas": reservas.descriptor()},
            "principio": "Availability y Fulfillment no se llaman entre sí; Fulfillment consume el "
                         "resultado de Availability (compuesto por `resolver`)."}


__all__ = ["availability", "fulfillment", "reservas", "descriptor"]
