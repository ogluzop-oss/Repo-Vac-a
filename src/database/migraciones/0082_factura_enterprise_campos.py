"""
Migracion 0082 — Campos enterprise en facturas_cliente (FASE 4.5/4.6/4.8 + origen). ADITIVA, reversible, idempotente.

- Internacional (4.6): tipo_cambio, fecha_tipo_cambio, importe_divisa, importe_eur, idioma.
- Autofacturacion (4.8): autofactura, emisor_tercero_nif, emisor_tercero_nombre.
- Workflow aprobacion (4.5): aprobada_por, aprobada_fecha (los estados se gestionan en ESTADOS).
- Origen (4.1/4.2): origen, id_recurrente, id_suscripcion (trazabilidad de la generacion).

Todo NULLABLE/0 → facturas existentes intactas.
"""

VERSION = "0082"
DESCRIPCION = "facturas_cliente: internacional + autofactura + aprobacion + origen (FASE 4)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("tipo_cambio", "DECIMAL(14,6) DEFAULT NULL"),
    ("fecha_tipo_cambio", "DATE DEFAULT NULL"),
    ("importe_divisa", "DECIMAL(14,2) DEFAULT NULL"),
    ("importe_eur", "DECIMAL(14,2) DEFAULT NULL"),
    ("idioma", "VARCHAR(5) DEFAULT NULL"),
    ("autofactura", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("emisor_tercero_nif", "VARCHAR(20) DEFAULT NULL"),
    ("emisor_tercero_nombre", "VARCHAR(160) DEFAULT NULL"),
    ("aprobada_por", "VARCHAR(80) DEFAULT NULL"),
    ("aprobada_fecha", "DATETIME DEFAULT NULL"),
    ("origen", "VARCHAR(15) DEFAULT NULL"),
    ("id_recurrente", "BIGINT DEFAULT NULL"),
    ("id_suscripcion", "BIGINT DEFAULT NULL"),
]


def aplicar(cur):
    for n, d in _COLS:
        cur.execute(f"ALTER TABLE facturas_cliente ADD COLUMN IF NOT EXISTS {n} {d}")


def revertir(cur):
    for n, _ in reversed(_COLS):
        cur.execute(f"ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS {n}")
