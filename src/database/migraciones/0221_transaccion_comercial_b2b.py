"""
Migración 0221 — Smart Suppliers · Fase A: conector `origen='b2b'` sobre `transaccion_comercial`
(migración 0139). ADITIVA, idempotente, reversible.

El propio commit que retiró la Lonja (408548b, "FASE 1: desmontaje del portal externo, lonja y pagos
marketplace") dejó anotado que el conector B2B sobre `transaccion_comercial` "llega en Fase 2" — esta
migración es esa pieza: añade SOLO las columnas que el modelo genérico (pensado para venta a cliente)
no tenía para una compra B2B (proveedor de destino + tienda destino), sin tocar ninguna columna
existente ni crear una tabla de transacciones paralela.

También extiende `reab_propuestas` (migración 0027) con `id_tienda`, requisito de la Extranet Empresa:
el carrito de reposición del portal solo opera sobre la tienda con conexión remota activa.
"""

VERSION = "0221"
DESCRIPCION = "Smart Suppliers: origen b2b en transaccion_comercial/lineas + id_tienda en reab_propuestas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TX = [
    ("id_suministrador", "BIGINT DEFAULT NULL"),
    ("id_tienda_destino", "INT DEFAULT NULL"),
]
_LINEAS = [
    ("unidad_medida", "VARCHAR(20) DEFAULT NULL"),
    ("moq_aplicado", "INT DEFAULT NULL"),
]
_PROP = [("id_tienda", "INT DEFAULT NULL")]


def aplicar(cur):
    for col, ddl in _TX:
        cur.execute(f"ALTER TABLE transaccion_comercial ADD COLUMN IF NOT EXISTS {col} {ddl}")
    for col, ddl in _LINEAS:
        cur.execute(f"ALTER TABLE transaccion_lineas ADD COLUMN IF NOT EXISTS {col} {ddl}")
    for col, ddl in _PROP:
        cur.execute(f"ALTER TABLE reab_propuestas ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _PROP:
        cur.execute(f"ALTER TABLE reab_propuestas DROP COLUMN IF EXISTS {col}")
    for col, _ in _LINEAS:
        cur.execute(f"ALTER TABLE transaccion_lineas DROP COLUMN IF EXISTS {col}")
    for col, _ in _TX:
        cur.execute(f"ALTER TABLE transaccion_comercial DROP COLUMN IF EXISTS {col}")
