"""
Migración 0005 — Custodia de certificados fiscales (C3.5.1). ADITIVA y reversible.

Tabla `fiscal_certificados`: metadatos en claro (para gestión sin descifrar) +
el MATERIAL PKCS#12 SIEMPRE cifrado (D2: blob cifrado en BD; D3/D4: nunca en disco
ni en claro; clave derivada por tenant). Multiempresa por `id_empresa`.

No toca el núcleo C3.2 ni las tablas fiscales existentes. Idempotente.
"""

VERSION = "0005"
DESCRIPCION = "Custodia de certificados fiscales (fiscal_certificados, material cifrado)"
REVERSIBLE = True
REQUIERE_BACKUP = True            # contiene material criptográfico (aunque cifrado)


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fiscal_certificados (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL,
            alias           VARCHAR(80)           DEFAULT NULL,
            tipo            VARCHAR(20)  NOT NULL DEFAULT 'sello',  -- sello | representante
            titular_nif     VARCHAR(20)           DEFAULT NULL,
            ca_emisora      VARCHAR(255)          DEFAULT NULL,
            num_serie       VARCHAR(80)           DEFAULT NULL,
            valido_desde    DATETIME              DEFAULT NULL,
            valido_hasta    DATETIME              DEFAULT NULL,
            huella_cert     CHAR(64)              DEFAULT NULL,      -- SHA-256 del cert DER
            material_cifrado MEDIUMTEXT  NOT NULL,                  -- {p12,password} cifrado por tenant
            estado          VARCHAR(15)  NOT NULL DEFAULT 'activo',  -- activo|inactivo|revocado|caducado
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cert_emp (id_empresa),
            INDEX idx_cert_estado (estado),
            INDEX idx_cert_emp_estado (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS fiscal_certificados")
