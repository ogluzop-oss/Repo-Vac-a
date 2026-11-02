"""
Migración 0274 — Divisa en facturas (FASE C — facturación internacional). ADITIVA, reversible,
idempotente.

Añade `divisa VARCHAR(3) DEFAULT NULL` (código ISO 4217: EUR/USD/GBP/CHF...) a `facturas_cliente`
Y a `compras_facturas` — esta última no tenía NINGÚN campo de divisa hasta ahora. Persiste lo que
`services/facturacion/internacional.py::aplicar_divisa()` ya calculaba (tipo_cambio/importe_divisa/
importe_eur) pero nunca guardaba: el propio código de divisa (bug confirmado — sin esta columna
era imposible saber en qué divisa se había emitido ya una factura convertida). NULL/opcional →
una factura sin divisa explícita se sigue tratando como EUR (comportamiento actual, sin cambios).
"""

VERSION = "0274"
DESCRIPCION = "divisa (ISO 4217) en facturas_cliente y compras_facturas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = ("facturas_cliente", "compras_facturas")


def aplicar(cur):
    for t in _TABLAS:
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS divisa VARCHAR(3) DEFAULT NULL")


def revertir(cur):
    for t in _TABLAS:
        cur.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS divisa")
