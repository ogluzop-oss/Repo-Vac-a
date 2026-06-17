"""
Migración 0015 — Cola contable + mapeo de cuentas (E6.4). ADITIVA y reversible.

- contab_cola: eventos económicos pendientes de asentar (posting asíncrono).
- contab_mapeo: parametrización evento/clave → cuenta contable, por empresa.
Multiempresa. No toca ventas/compras (la integración es por hook best-effort).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0015"
DESCRIPCION = "Contabilidad: cola de posting + mapeo de cuentas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_cola (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            evento        VARCHAR(20)  NOT NULL,                 -- venta|compra|devolucion|merma
            subtipo       VARCHAR(20)           DEFAULT NULL,    -- ticket|factura
            ref           VARCHAR(64)           DEFAULT NULL,
            fecha_evento  DATE         NOT NULL,
            payload       MEDIUMTEXT            DEFAULT NULL,     -- datos económicos (JSON)
            estado        VARCHAR(12)  NOT NULL DEFAULT 'pendiente',  -- pendiente|hecho|error
            intentos      INT          NOT NULL DEFAULT 0,
            id_asiento    BIGINT                DEFAULT NULL,
            ultimo_error  VARCHAR(300)          DEFAULT NULL,
            proximo_intento DATETIME            DEFAULT NULL,
            fecha         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cc_emp (id_empresa),
            INDEX idx_cc_estado (id_empresa, estado),
            INDEX idx_cc_evento (id_empresa, evento, fecha_evento)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS contab_mapeo (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            ambito        VARCHAR(20)  NOT NULL,                 -- venta|compra|iva_rep|iva_sop|forma_pago|cliente|proveedor|merma|existencias
            clave         VARCHAR(40)  NOT NULL DEFAULT '',      -- p.ej. tipo IVA o forma de pago
            codigo_cuenta VARCHAR(10)  NOT NULL,
            UNIQUE KEY uq_mapeo (id_empresa, ambito, clave),
            INDEX idx_mp_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS contab_mapeo")
    cur.execute("DROP TABLE IF EXISTS contab_cola")
