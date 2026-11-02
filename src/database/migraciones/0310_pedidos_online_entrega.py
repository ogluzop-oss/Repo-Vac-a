"""
Migración 0310 — Modo de entrega y dirección de facturación del pedido online. ADITIVA,
idempotente, reversible.

El "Nuevo pedido" del Portal del Empleado (encargo a otra tienda/almacén, `crear_encargo_almacen`)
necesita que el cajero indique, con el cliente delante del mostrador, si el pedido se recoge en SU
propia tienda o se envía al domicilio del cliente — y, si es a domicilio, una dirección de
facturación aparte de la de envío (solo la de envío es obligatoria). Ninguna columna existía para
esto; `direccion_envio` (texto libre) ya cubría el envío, pero no distinguía el modo ni tenía
hueco para una dirección de facturación distinta.

`modo_entrega`: 'domicilio' (valor por defecto, compatible con todos los pedidos YA existentes —
web propia/marketplace siempre han sido a domicilio) | 'recogida_tienda' (solo tiene sentido en
encargos entre tiendas/almacenes: el cliente pasa a recogerlo por la tienda que lo pidió).
"""

VERSION = "0310"
DESCRIPCION = "pedidos_online.modo_entrega + direccion_facturacion"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE pedidos_online ADD COLUMN IF NOT EXISTS "
                "modo_entrega VARCHAR(20) NOT NULL DEFAULT 'domicilio'")
    cur.execute("ALTER TABLE pedidos_online ADD COLUMN IF NOT EXISTS "
                "direccion_facturacion TEXT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE pedidos_online DROP COLUMN IF EXISTS direccion_facturacion")
    cur.execute("ALTER TABLE pedidos_online DROP COLUMN IF EXISTS modo_entrega")
