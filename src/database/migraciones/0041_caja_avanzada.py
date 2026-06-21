"""
Migracion 0041 - Caja avanzada (VTA.7): caja_sesiones + caja_movimientos. ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0041"
DESCRIPCION = "Caja avanzada (VTA.7): caja_sesiones + caja_movimientos"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS caja_sesiones (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_tienda INT DEFAULT NULL,
            caja VARCHAR(40) DEFAULT NULL,
            estado VARCHAR(10) NOT NULL DEFAULT 'abierta',
            fondo_inicial DECIMAL(12,2) NOT NULL DEFAULT 0,
            importe_declarado DECIMAL(12,2) DEFAULT NULL,
            diferencia DECIMAL(12,2) DEFAULT NULL,
            usuario_apertura VARCHAR(120) DEFAULT NULL,
            usuario_cierre VARCHAR(120) DEFAULT NULL,
            fecha_apertura DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_cierre DATETIME DEFAULT NULL,
            INDEX idx_cs_emp (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS caja_movimientos (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_sesion BIGINT NOT NULL,
            tipo VARCHAR(12) NOT NULL,
            importe DECIMAL(12,2) NOT NULL DEFAULT 0,
            concepto VARCHAR(255) DEFAULT NULL,
            usuario VARCHAR(120) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cm_sesion (id_sesion),
            CONSTRAINT fk_cm_sesion FOREIGN KEY (id_sesion)
                REFERENCES caja_sesiones(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS caja_movimientos")
    cur.execute("DROP TABLE IF EXISTS caja_sesiones")
