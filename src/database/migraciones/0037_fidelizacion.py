"""
Migracion 0037 - Fidelizacion (VTA.3): fidelizacion_movimientos + cupones + saldo. ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0037"
DESCRIPCION = "Fidelizacion (VTA.3): fidelizacion_movimientos + cupones + saldo"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS saldo_puntos INT NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS saldo_monedero DECIMAL(12,2) NOT NULL DEFAULT 0")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS fidelizacion_movimientos (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_cliente BIGINT NOT NULL,
            tipo VARCHAR(16) NOT NULL,
            puntos INT NOT NULL DEFAULT 0,
            importe DECIMAL(12,2) NOT NULL DEFAULT 0,
            id_venta BIGINT DEFAULT NULL,
            descripcion VARCHAR(255) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fid_cli (id_empresa, id_cliente)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS cupones (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            codigo VARCHAR(40) NOT NULL,
            id_cliente BIGINT DEFAULT NULL,
            tipo VARCHAR(16) NOT NULL DEFAULT 'descuento_pct',
            valor DECIMAL(10,2) NOT NULL DEFAULT 0,
            estado VARCHAR(12) NOT NULL DEFAULT 'activo',
            fecha_caducidad DATE DEFAULT NULL,
            id_venta_uso BIGINT DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_cupon (id_empresa, codigo),
            INDEX idx_cup_cli (id_cliente)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cupones")
    cur.execute("DROP TABLE IF EXISTS fidelizacion_movimientos")
