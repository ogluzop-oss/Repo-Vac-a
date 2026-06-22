"""
Migración 0045 — Cuentas bancarias (rama Tesorería, FASE 1). ADITIVA, idempotente, reversible.

Crea `cuentas_bancarias` (multiempresa + multitienda). El IBAN se almacena CIFRADO en reposo
(mismo patrón que pasarela_config); `iban_mascara` guarda solo país+****+4 últimos para la UI.
No toca ninguna tabla existente.
"""

VERSION = "0045"
DESCRIPCION = "Cuentas bancarias (tesorería) multiempresa/multitienda"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuentas_bancarias (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_tienda     INT          DEFAULT NULL,
            nombre_cuenta VARCHAR(120) NOT NULL,
            titular       VARCHAR(160) DEFAULT NULL,
            iban          VARCHAR(255) NOT NULL,
            iban_mascara  VARCHAR(40)  DEFAULT NULL,
            bic           VARCHAR(16)  DEFAULT NULL,
            entidad       VARCHAR(120) DEFAULT NULL,
            sucursal      VARCHAR(120) DEFAULT NULL,
            moneda        VARCHAR(3)   NOT NULL DEFAULT 'EUR',
            saldo_inicial DECIMAL(14,2) NOT NULL DEFAULT 0,
            activa        TINYINT      NOT NULL DEFAULT 1,
            fecha_alta    DATETIME     DEFAULT CURRENT_TIMESTAMP,
            observaciones TEXT         DEFAULT NULL,
            INDEX idx_cb_emp (id_empresa, activa),
            INDEX idx_cb_tienda (id_empresa, id_tienda)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cuentas_bancarias")
