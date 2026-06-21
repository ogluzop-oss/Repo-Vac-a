"""
Migración 0032 — Facturación avanzada de compras (CMP.5). ADITIVA, reversible, idempotente.
tipo_documento (factura|abono|rectificativa), factura rectificada y conciliación n:m
factura↔recepción.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0032"
DESCRIPCION = "Facturas: tipo_documento + rectificada + conciliación n:m"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute("ALTER TABLE compras_facturas ADD COLUMN IF NOT EXISTS tipo_documento "
                "VARCHAR(14) NOT NULL DEFAULT 'factura'")  # factura|abono|rectificativa
    cur.execute("ALTER TABLE compras_facturas ADD COLUMN IF NOT EXISTS id_factura_rectificada "
                "BIGINT DEFAULT NULL")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_factura_recepciones (
            id           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa   CHAR(36) NOT NULL DEFAULT '{emp}',
            id_factura   BIGINT NOT NULL,
            id_recepcion BIGINT NOT NULL,
            importe      DECIMAL(12,2) NOT NULL DEFAULT 0,
            UNIQUE KEY uq_fr (id_factura, id_recepcion),
            INDEX idx_fr_factura (id_factura),
            INDEX idx_fr_recepcion (id_recepcion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_factura_recepciones")
    cur.execute("ALTER TABLE compras_facturas DROP COLUMN IF EXISTS id_factura_rectificada")
    cur.execute("ALTER TABLE compras_facturas DROP COLUMN IF EXISTS tipo_documento")
