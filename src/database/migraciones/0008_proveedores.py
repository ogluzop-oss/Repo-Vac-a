"""
Migración 0008 — Proveedores (E2.1). ADITIVA y reversible.

Modelo base de proveedores + contactos + direcciones. Multiempresa por `id_empresa`
(coherente con catálogo/fiscal). No toca el núcleo ni tablas existentes.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0008"
DESCRIPCION = "Proveedores (proveedores, contactos, direcciones)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS proveedores (
            id_proveedor    BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            razon_social    VARCHAR(255) NOT NULL,
            nombre_comercial VARCHAR(255)         DEFAULT NULL,
            cif_nif         VARCHAR(20)           DEFAULT NULL,
            email           VARCHAR(150)          DEFAULT NULL,
            telefono        VARCHAR(30)           DEFAULT NULL,
            direccion_fiscal VARCHAR(255)         DEFAULT NULL,
            estado          VARCHAR(15)  NOT NULL DEFAULT 'activo',
            observaciones   TEXT                  DEFAULT NULL,
            fecha_alta      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_prov_emp (id_empresa),
            INDEX idx_prov_estado (estado),
            INDEX idx_prov_nif (cif_nif)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proveedores_contactos (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_proveedor    BIGINT       NOT NULL,
            nombre          VARCHAR(150) NOT NULL,
            cargo           VARCHAR(100)          DEFAULT NULL,
            email           VARCHAR(150)          DEFAULT NULL,
            telefono        VARCHAR(30)           DEFAULT NULL,
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_provc_prov (id_proveedor),
            CONSTRAINT fk_provc_prov FOREIGN KEY (id_proveedor)
                REFERENCES proveedores(id_proveedor) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proveedores_direcciones (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_proveedor    BIGINT       NOT NULL,
            tipo            VARCHAR(15)  NOT NULL DEFAULT 'fiscal',  -- fiscal|envio|almacen
            direccion       VARCHAR(255)          DEFAULT NULL,
            cp              VARCHAR(10)           DEFAULT NULL,
            municipio       VARCHAR(120)          DEFAULT NULL,
            provincia       VARCHAR(120)          DEFAULT NULL,
            pais            VARCHAR(60)  NOT NULL DEFAULT 'España',
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_provd_prov (id_proveedor),
            CONSTRAINT fk_provd_prov FOREIGN KEY (id_proveedor)
                REFERENCES proveedores(id_proveedor) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS proveedores_direcciones")
    cur.execute("DROP TABLE IF EXISTS proveedores_contactos")
    cur.execute("DROP TABLE IF EXISTS proveedores")
