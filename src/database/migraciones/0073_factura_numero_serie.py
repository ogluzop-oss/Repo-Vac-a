"""
Migracion 0073 — Numeracion por SERIE fiscal en facturas_cliente. ADITIVA, reversible, idempotente.

Anade `numero_serie` (secuencial por empresa+serie, sin huecos) y una clave UNICA
(id_empresa, serie, numero_serie) como red de seguridad anti-duplicado. La serie se resuelve
con la estrategia fiscal (serie/serie_por: empresa/tienda/caja). Las filas existentes quedan
con numero_serie NULL (multiples NULL permitidos en la UNIQUE de InnoDB) → no se tocan ni se
renumeran. No afecta a venta_items, kardex ni al nucleo fiscal.
"""

VERSION = "0073"
DESCRIPCION = "facturas_cliente.numero_serie (numeracion secuencial por serie) + UNIQUE"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente "
                "ADD COLUMN IF NOT EXISTS numero_serie BIGINT DEFAULT NULL")
    # UNIQUE anti-duplicado por serie. Idempotente: se ignora si ya existe.
    try:
        cur.execute("ALTER TABLE facturas_cliente "
                    "ADD UNIQUE KEY uq_fc_serie_num (id_empresa, serie, numero_serie)")
    except Exception:
        pass  # la clave ya existe (re-aplicacion)


def revertir(cur):
    try:
        cur.execute("ALTER TABLE facturas_cliente DROP INDEX uq_fc_serie_num")
    except Exception:
        pass
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS numero_serie")
