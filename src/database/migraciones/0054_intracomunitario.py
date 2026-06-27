"""
Migración 0054 — Dimensión intracomunitaria (FASE AEAT-6). ADITIVA, idempotente, reversible.

Añade a `clientes` y `proveedores` los campos necesarios para el Modelo 349:
  • nif_iva             — NIF-IVA / VAT number europeo del operador.
  • es_intracomunitario — marca de operador intracomunitario (0/1).
  • pais_fiscal         — código de país fiscal ISO-2 (def. 'ES').
Todos opcionales y con default → las filas existentes y el comportamiento previo no cambian.
"""

VERSION = "0054"
DESCRIPCION = "Dimensión intracomunitaria en clientes/proveedores (nif_iva, es_intracomunitario, pais_fiscal)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = ("clientes", "proveedores")


def aplicar(cur):
    for t in _TABLAS:
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS nif_iva VARCHAR(20) DEFAULT NULL")
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS es_intracomunitario TINYINT NOT NULL DEFAULT 0")
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS pais_fiscal VARCHAR(2) NOT NULL DEFAULT 'ES'")
        cur.execute(f"ALTER TABLE {t} ADD INDEX IF NOT EXISTS idx_{t}_intra (id_empresa, es_intracomunitario)")


def revertir(cur):
    for t in _TABLAS:
        cur.execute(f"ALTER TABLE {t} DROP INDEX IF EXISTS idx_{t}_intra")
        cur.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS pais_fiscal")
        cur.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS es_intracomunitario")
        cur.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS nif_iva")
