"""
Migracion 0083 — Estructura MULTIPAÍS fiscal (FASE 4.7). ADITIVA, reversible, idempotente.

SOLO estructura (no se implementa fiscalidad específica por país todavía). Prepara el terreno
para IVA UE / GST / Sales Tax / VAT internacional sin tocar la fiscalidad actual (España).
"""

VERSION = "0083"
DESCRIPCION = "Estructura multipaís: pais_fiscal + regimen_fiscal_pais + configuracion_iva_pais (FASE 4.7)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pais_fiscal (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(3) NOT NULL,
            nombre VARCHAR(80) DEFAULT NULL,
            zona VARCHAR(20) DEFAULT NULL,
            sistema_impuesto VARCHAR(20) DEFAULT 'IVA',
            divisa VARCHAR(3) DEFAULT NULL,
            activo TINYINT(1) NOT NULL DEFAULT 1,
            UNIQUE KEY uq_pais_fiscal (codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS regimen_fiscal_pais (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            pais VARCHAR(3) NOT NULL,
            codigo VARCHAR(30) NOT NULL,
            nombre VARCHAR(120) DEFAULT NULL,
            descripcion VARCHAR(255) DEFAULT NULL,
            activo TINYINT(1) NOT NULL DEFAULT 1,
            UNIQUE KEY uq_regimen_pais (pais, codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_iva_pais (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            pais VARCHAR(3) NOT NULL,
            tipo VARCHAR(20) DEFAULT NULL,
            porcentaje DECIMAL(5,2) NOT NULL DEFAULT 0,
            etiqueta VARCHAR(60) DEFAULT NULL,
            vigente_desde DATE DEFAULT NULL,
            activo TINYINT(1) NOT NULL DEFAULT 1,
            INDEX idx_iva_pais (pais)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS configuracion_iva_pais")
    cur.execute("DROP TABLE IF EXISTS regimen_fiscal_pais")
    cur.execute("DROP TABLE IF EXISTS pais_fiscal")
