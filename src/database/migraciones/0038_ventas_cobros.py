"""
Migracion 0038 - Cobros avanzados (VTA.4): ventas_cobros. ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0038"
DESCRIPCION = "Cobros avanzados (VTA.4): ventas_cobros"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS ventas_cobros (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_venta BIGINT NOT NULL,
            metodo VARCHAR(16) NOT NULL,
            importe DECIMAL(12,2) NOT NULL DEFAULT 0,
            referencia VARCHAR(80) DEFAULT NULL,
            estado VARCHAR(12) NOT NULL DEFAULT 'cobrado',
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_vc_venta (id_venta),
            INDEX idx_vc_emp (id_empresa, metodo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS ventas_cobros")
