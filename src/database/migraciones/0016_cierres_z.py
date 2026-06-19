"""
Migración 0016 — Cierre Z formal de caja (F2.2). ADITIVA y reversible.

`cierres_z`: cierre diario de caja inmutable y auditable (nº correlativo por
empresa+tienda, hash encadenado, arqueo declarado/esperado/diferencia, desglose de
cobros e IVA en JSON). No modifica ventas/devoluciones/contabilidad. Multiempresa.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0016"
DESCRIPCION = "Cierre Z formal de caja (cierres_z)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS cierres_z (
            id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa       CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda        VARCHAR(64)  NOT NULL DEFAULT '',
            numero           BIGINT       NOT NULL,
            fecha            DATE         NOT NULL,
            caja             INT          NOT NULL DEFAULT 1,
            usuario          VARCHAR(100)          DEFAULT NULL,
            ventas_brutas    DECIMAL(12,2) NOT NULL DEFAULT 0,
            devoluciones     DECIMAL(12,2) NOT NULL DEFAULT 0,
            descuentos       DECIMAL(12,2) NOT NULL DEFAULT 0,
            base             DECIMAL(12,2) NOT NULL DEFAULT 0,
            iva              DECIMAL(12,2) NOT NULL DEFAULT 0,
            total_cobrado    DECIMAL(12,2) NOT NULL DEFAULT 0,
            desglose_cobros  TEXT                  DEFAULT NULL,   -- JSON por forma de pago
            desglose_iva     TEXT                  DEFAULT NULL,   -- JSON por tipo de IVA
            importe_esperado DECIMAL(12,2) NOT NULL DEFAULT 0,
            importe_declarado DECIMAL(12,2) NOT NULL DEFAULT 0,
            diferencia       DECIMAL(12,2) NOT NULL DEFAULT 0,
            estado           VARCHAR(12)  NOT NULL DEFAULT 'CUADRADO',  -- CUADRADO|DESCUADRE
            hash_audit       CHAR(64)              DEFAULT NULL,
            ruta_pdf         VARCHAR(500)          DEFAULT NULL,
            fecha_registro   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_cierrez (id_empresa, id_tienda, caja, fecha),
            INDEX idx_cz_emp (id_empresa),
            INDEX idx_cz_fecha (id_empresa, fecha)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cierres_z")
