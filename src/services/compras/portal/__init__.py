"""
Portal de proveedor — enlace bidireccional empresa↔proveedor (Fase 2 de la bolsa de proveedores).

Vive DENTRO del módulo de compras/proveedores y está disponible en TODAS las versiones. Es DEGRADABLE:
se construye completo y probado, pero el enlace remoto en vivo NO se despliega hasta el día de producción
(`estado.portal_activo()` → False por defecto). Reutiliza infraestructura existente (N7): tarifas en
`proveedor_precios_negociados`, pedidos/estados en `db.compras`, incidencias en `compras_incidencias`,
evaluación en `proveedores_evaluacion`, notificaciones y auditoría.

Fachada plana: `from src.services.compras import portal` y usar `portal.invitar_proveedor(...)`,
`portal.crear_rfq(...)`, `portal.enviar_mensaje(...)`, etc.
"""

from .estado import modo, portal_activo
from .cuentas import (activar, estado_cuenta, invitar_proveedor, listar_cuentas, marcar_conexion,
                      regenerar_token, resolver_token, revocar)
from .pedidos import (actualizar_estado_pedido, estado_pedido, estados_pedidos, pedidos_de_proveedor,
                      set_stock, stock_bolsa, stock_de)
from .rfq import (adjudicar_rfq, crear_rfq, listar_rfq, obtener_rfq, ofertas_de_rfq, responder_rfq,
                  rfq_abiertas)
from .mensajes import enviar_mensaje, hilo, marcar_leido, no_leidos
from .scorecard import scorecard
from .tarifas import listar_tarifas, subir_tarifa

__all__ = [
    "portal_activo", "modo",
    "invitar_proveedor", "estado_cuenta", "listar_cuentas", "revocar", "activar", "regenerar_token",
    "resolver_token", "marcar_conexion",
    "actualizar_estado_pedido", "estado_pedido", "estados_pedidos", "pedidos_de_proveedor",
    "set_stock", "stock_de", "stock_bolsa",
    "crear_rfq", "listar_rfq", "obtener_rfq", "rfq_abiertas", "responder_rfq", "ofertas_de_rfq",
    "adjudicar_rfq",
    "enviar_mensaje", "hilo", "marcar_leido", "no_leidos",
    "scorecard", "listar_tarifas", "subir_tarifa",
]
