"""
Migracion 0074 — Anulacion y factura rectificativa (abono). ADITIVA, reversible, idempotente.

Anade a facturas_cliente:
- tipo_documento        : 'factura' (normal) | 'rectificativa' (abono que revierte otra).
- id_factura_rectificada: factura original a la que rectifica un abono.
- motivo_anulacion      : motivo al pasar una factura a estado 'anulada'.

Permite sustituir el BORRADO FISICO por anulacion + abono (sin huecos de numeracion,
conforme a normativa). Columnas NULLABLE/con defecto: no tocan filas existentes ni el
nucleo fiscal/contable.
"""

VERSION = "0074"
DESCRIPCION = "facturas_cliente: tipo_documento + id_factura_rectificada + motivo_anulacion (anulacion/abono)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente "
                "ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(15) NOT NULL DEFAULT 'factura'")
    cur.execute("ALTER TABLE facturas_cliente "
                "ADD COLUMN IF NOT EXISTS id_factura_rectificada BIGINT DEFAULT NULL")
    cur.execute("ALTER TABLE facturas_cliente "
                "ADD COLUMN IF NOT EXISTS motivo_anulacion VARCHAR(255) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS motivo_anulacion")
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS id_factura_rectificada")
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS tipo_documento")
