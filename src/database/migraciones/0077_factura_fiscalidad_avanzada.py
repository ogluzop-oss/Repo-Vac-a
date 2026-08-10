"""
Migracion 0077 — Fiscalidad avanzada en la factura (FASE 3.2). ADITIVA, reversible, idempotente.

Persiste en facturas_cliente el resultado del motor fiscal único (recargo de equivalencia,
ISP/intracom/exento, retención IRPF) y la leyenda legal. Columnas NULLABLE/0 por defecto: las
facturas sin régimen especial quedan EXACTAMENTE igual. Las columnas tipo_recargo/cuota_recargo
de factura_impuestos ya existen (migr 0071).
"""

VERSION = "0077"
DESCRIPCION = "facturas_cliente: regimen_fiscal/cuota_recargo/retencion/leyenda_fiscal"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("regimen_fiscal", "VARCHAR(20) DEFAULT NULL"),
    ("cuota_recargo", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ("retencion_pct", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
    ("retencion_importe", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ("leyenda_fiscal", "VARCHAR(500) DEFAULT NULL"),
]


def aplicar(cur):
    for nombre, definicion in _COLS:
        cur.execute(f"ALTER TABLE facturas_cliente ADD COLUMN IF NOT EXISTS {nombre} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_COLS):
        cur.execute(f"ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS {nombre}")
