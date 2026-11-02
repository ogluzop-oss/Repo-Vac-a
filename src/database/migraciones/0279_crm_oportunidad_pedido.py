"""
Migración 0279 — Conversión CRM → Pedido de cliente (borrador). ADITIVA e IDEMPOTENTE.

Añade `crm_oportunidades.id_pedido_borrador` (pedido de cliente en borrador generado a partir de la
oportunidad, vía `db.ventas_comercial.crear_pedido_cliente` — VTA.6, el mismo motor que ya usa la
pestaña Presupuestos). Mismo patrón EXACTO que 0170 (`id_factura`) y 0173 (`id_proyecto`): enlace +
idempotencia (no se genera dos veces el borrador de la misma oportunidad). No modifica datos existentes.

NO se reutiliza `services.compras.b2b_pedidos` para esto: ese motor es de APROVISIONAMIENTO
(Empresa←Proveedor, vía sesión de Portal Proveedor/`token_sesion` + `id_suministrador`) — dirección
opuesta a una venta CRM a un cliente propio. Ver `services/crm/conversion.py::convertir_a_pedido_borrador`.
"""

VERSION = "0279"
DESCRIPCION = "CRM→Pedido borrador: columna crm_oportunidades.id_pedido_borrador"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE crm_oportunidades ADD COLUMN IF NOT EXISTS id_pedido_borrador INT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE crm_oportunidades DROP COLUMN IF EXISTS id_pedido_borrador")
