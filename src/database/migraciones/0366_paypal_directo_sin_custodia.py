"""
Migración 0366 — PayPal B2B sin custodia de Smart Manager (petición explícita, 2026-11-27):
rediseño del pago PayPal del marketplace (Portal Empresa B2B / Portal Proveedor) para que el dinero
vaya SIEMPRE directo de la cuenta de la empresa compradora a la cuenta del proveedor — la cuenta de
PayPal de Smart Manager deja de retener ni enviar ningún importe entre las dos partes.

Por qué hace falta (confirmado con el usuario, 2026-11-27): la API de Órdenes de PayPal no permite
dirigir el cobro de una Orden a la cuenta de un tercero (`payee`) sin que PayPal apruebe a Smart
Manager como partner/marketplace — eso es justo lo que ya se decidió evitar (migr. 0358/0360). La
ÚNICA forma de pagar directo sin Partner Program es que cada proveedor use SU PROPIA app de PayPal
(Client ID/Secret de su propio desarrollador, gratis e inmediato, sin aprobación de PayPal ni de
Smart Manager) — la Orden se crea y captura con ESAS credenciales, así que el dinero nace y vive en
la cuenta del proveedor desde el principio; Smart Manager nunca lo custodia ni hace un Payout.

`suministradores.paypal_client_id`/`paypal_client_secret`: credenciales PROPIAS del proveedor,
cifradas en reposo (Fernet, `utils/cripto.py` — mismo criterio que `tpv_datafono_config.api_key`/
`api_secret`). Sustituyen en la práctica a `paypal_email` (que se deja intacta, sin usarse para
cobrar — ver `services.compras.suministradores.fijar_paypal_credenciales`).

`b2b_pago_comprador_proveedor` (tabla nueva): el método de pago PayPal guardado («Vault») de la
empresa compradora está vinculado a la app que lo guardó — con credenciales por proveedor, un
Vault guardado bajo la app de Smart Manager (como hasta ahora, migr. 0355/`b2b_empresas_pago`) ya
no sirve para cobrar a través de la app de OTRO proveedor. Por eso el Vault pasa a guardarse POR
PAREJA (empresa, proveedor) — la empresa aprueba el pago con PayPal la primera vez que compra a un
proveedor por esta vía; las compras siguientes a ESE MISMO proveedor ya no requieren aprobación.
`b2b_empresas_pago.paypal_*` (migr. 0355) se deja intacta (vía antigua, ya sin tráfico nuevo).
"""

VERSION = "0366"
DESCRIPCION = "PayPal B2B directo: credenciales propias del proveedor + vault por proveedor"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "suministradores", "paypal_client_id"):
        cur.execute("ALTER TABLE suministradores ADD COLUMN paypal_client_id "
                   "VARCHAR(255) DEFAULT NULL")
    if not _tiene_columna(cur, "suministradores", "paypal_client_secret"):
        cur.execute("ALTER TABLE suministradores ADD COLUMN paypal_client_secret "
                   "VARCHAR(500) DEFAULT NULL")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS b2b_pago_comprador_proveedor (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(64) NOT NULL,
            id_suministrador BIGINT NOT NULL,
            paypal_payment_token_id VARCHAR(128) DEFAULT NULL,
            paypal_verificado TINYINT(1) NOT NULL DEFAULT 0,
            paypal_verificado_en DATETIME DEFAULT NULL,
            UNIQUE KEY uq_comprador_proveedor (id_empresa, id_suministrador)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS b2b_pago_comprador_proveedor")
    for columna in ("paypal_client_id", "paypal_client_secret"):
        if _tiene_columna(cur, "suministradores", columna):
            cur.execute(f"ALTER TABLE suministradores DROP COLUMN {columna}")
