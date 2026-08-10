"""
Seguridad de la ejecucion (Paquete Enterprise 10, SUBFASE 10.14). Ninguna accion critica puede
realizarse sin autorizacion valida: generar pedidos, modificar precios, despedir empleados, emitir
facturas, realizar pagos o mover stock. Estas acciones NO tienen ejecutor automatico en el catalogo
(catalogo.CRITICAS): siempre se convierten en propuesta gobernada (Workflow + Gobierno). Este
modulo hace explicita y comprobable esa frontera.
"""

from src.services.autonomia import catalogo


def accion_permitida_auto(codigo, modo) -> bool:
    """True solo si la accion puede auto-ejecutarse en el modo dado (nunca las criticas)."""
    from src.services.autonomia import modos
    m = catalogo.meta(codigo)
    return modos.permite_ejecucion(modo, critica=m["critica"], informativa=m["informativa"])


def garantia() -> dict:
    return {
        "acciones_criticas_nunca_automaticas": list(catalogo.CRITICAS),
        "regla": ("Toda accion critica (pedidos, precios, despidos, facturas, pagos, stock) se "
                  "convierte SIEMPRE en propuesta gobernada por Workflow + Gobierno Corporativo. "
                  "El sistema solo auto-ejecuta acciones seguras y reversibles, segun el modo de "
                  "empresa, y siempre sobre un plan APROBADO."),
        "requiere_para_ejecutar": ["plan APROBADO", "autoridad de Gobierno", "workflow aprobado (si aplica)",
                                   "modo de empresa que lo permita"],
        "todo_auditado": True,
    }
