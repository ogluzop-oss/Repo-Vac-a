"""
Migración 0014 — Asientos contables (E6.2). ADITIVA y reversible.

contab_asientos (cabecera) + contab_apuntes (líneas Debe/Haber). Doble partida con
cuadre; numeración por empresa+ejercicio; inmutabilidad por estado; hash de auditoría
encadenado. Multiempresa.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0014"
DESCRIPCION = "Asientos contables (contab_asientos, contab_apuntes)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_asientos (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_ejercicio  BIGINT                DEFAULT NULL,
            anio          INT          NOT NULL,
            numero        BIGINT       NOT NULL,
            fecha         DATE         NOT NULL,
            concepto      VARCHAR(255)          DEFAULT NULL,
            tipo          VARCHAR(16)  NOT NULL DEFAULT 'normal',
            origen        VARCHAR(20)  NOT NULL DEFAULT 'manual',
            ref_origen    VARCHAR(64)           DEFAULT NULL,
            estado        VARCHAR(14)  NOT NULL DEFAULT 'borrador',  -- borrador|contabilizado|anulado
            total_debe    DECIMAL(14,2) NOT NULL DEFAULT 0,
            total_haber   DECIMAL(14,2) NOT NULL DEFAULT 0,
            anulado_por   BIGINT                DEFAULT NULL,
            hash_audit    CHAR(64)              DEFAULT NULL,
            usuario       VARCHAR(100)          DEFAULT NULL,
            fecha_registro DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_asiento (id_empresa, anio, numero),
            INDEX idx_as_emp (id_empresa),
            INDEX idx_as_fecha (id_empresa, fecha),
            INDEX idx_as_origen (origen, ref_origen)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_apuntes (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_asiento    BIGINT       NOT NULL,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            codigo_cuenta VARCHAR(10)  NOT NULL,
            descripcion   VARCHAR(255)          DEFAULT NULL,
            debe          DECIMAL(14,2) NOT NULL DEFAULT 0,
            haber         DECIMAL(14,2) NOT NULL DEFAULT 0,
            tercero       VARCHAR(20)           DEFAULT NULL,
            tipo_iva      DECIMAL(5,2)          DEFAULT NULL,
            INDEX idx_ap_asiento (id_asiento),
            INDEX idx_ap_cuenta (id_empresa, codigo_cuenta),
            CONSTRAINT fk_ap_asiento FOREIGN KEY (id_asiento)
                REFERENCES contab_asientos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS contab_apuntes")
    cur.execute("DROP TABLE IF EXISTS contab_asientos")
