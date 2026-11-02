"""
Migración 0253 — Umbral de morosidad tolerado por empresa (Facturación). ADITIVA, reversible.

Cada empresa que contrata Smart Manager puede fijar su propio porcentaje de morosidad tolerado sobre
SUS PROPIOS clientes (facturas impagadas/vencidas de `facturas_cliente` frente a su facturación total) —
distinto y sin relación con la suscripción de esa empresa a Smart Manager (esa caducidad ya se avisa por
otro sistema, en el menú principal). Por defecto 15% si la empresa no lo ha configurado todavía
(`services/facturacion/config.py`).
"""

VERSION = "0253"
DESCRIPCION = "facturacion_config: morosidad_tolerada_pct por empresa"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturacion_config (
            id_empresa             CHAR(36)      NOT NULL PRIMARY KEY,
            morosidad_tolerada_pct DECIMAL(5,2)  DEFAULT NULL,
            actualizado_en         DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS facturacion_config")
