"""
Migración 0204 — Cuentas conectadas del PSP (modelo TOKENIZADO). ADITIVA, idempotente, reversible.

Marketplace + Pagos (F0). En lugar de almacenar el IBAN completo (aunque cifrado) — modelo incorrecto para
un marketplace B2B con fondos de terceros — Smart Manager guarda SOLO el **token opaco** de la cuenta
conectada del PSP (`account_id`, p. ej. `acct_1N4x82Lkj92B`) y **metadatos visuales/de estado**
(banco, últimos 4, divisa, estado KYB, payouts habilitados). La custodia del dato bancario sensible y de
los fondos es del PSP regulado (Stripe Connect), no de Smart Manager.

Tabla polimórfica única `psp_cuentas_conectadas` (una fila por parte: empresa | proveedor | vendedor de la
Lonja), para no dispersar columnas en tres tablas distintas. Reutiliza el patrón de las demás migraciones.
La captura directa de IBAN (`proveedores.iban_cifrado`, `lonja_vendedores.iban_cifrado`, migr 0203) queda
DEPRECADA (se conserva un ciclo, no se escribe ya desde la UI).
"""

VERSION = "0204"
DESCRIPCION = "Cuentas conectadas del PSP (modelo tokenizado: token opaco + metadatos, sin IBAN completo)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("psp_cuentas_conectadas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo_parte VARCHAR(12) NOT NULL DEFAULT 'empresa',
        id_parte BIGINT NOT NULL DEFAULT 0,
        psp VARCHAR(16) NOT NULL DEFAULT 'stripe',
        account_id VARCHAR(120) DEFAULT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        payouts_enabled TINYINT NOT NULL DEFAULT 0,
        charges_enabled TINYINT NOT NULL DEFAULT 0,
        banco VARCHAR(120) DEFAULT NULL,
        ultimos4 VARCHAR(8) DEFAULT NULL,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        onboarding_url VARCHAR(512) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_psp_parte (id_empresa, tipo_parte, id_parte, psp),
        INDEX idx_psp_account (account_id),
        INDEX idx_psp_emp (id_empresa, status)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
