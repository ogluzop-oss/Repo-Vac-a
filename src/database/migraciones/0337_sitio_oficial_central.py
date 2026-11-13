"""
Migración 0337 — Soporte del SITIO OFICIAL (web comercial pública) sobre la BD CENTRAL de
licencias (`src/backend_central/`, migración 0234). Igual que esa migración, solo tiene sentido
aplicada sobre `smart_manager_central`; en una BD local de cliente quedan tablas/columnas sin usar.

- `cuentas_web_central`: cuenta de acceso del cliente al sitio oficial (email+contraseña, PBKDF2 vía
  `werkzeug.security` — NUNCA el hash plano SHA-256 que usa `db/usuario.py` para empleados del ERP,
  un sistema de identidad totalmente distinto). Vinculada a su empresa central.
- `codigos_activacion`: + `stripe_session_id` (idempotencia: no generar dos códigos para el mismo
  Checkout Session si el webhook y la página de éxito llegan los dos) y `email_cliente` (para poder
  reenviar el código si lo pierde).
"""

VERSION = "0337"
DESCRIPCION = "Sitio oficial: cuentas web centrales + idempotencia de activación por Stripe Checkout"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuentas_web_central (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            email               VARCHAR(255) NOT NULL,
            password_hash       VARCHAR(255) NOT NULL,
            id_empresa_central  CHAR(36)     NOT NULL,
            creado_en           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_cuenta_web_email (email),
            INDEX idx_cuenta_web_empresa (id_empresa_central)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='codigos_activacion'
              AND COLUMN_NAME='stripe_session_id'
    """)
    r = cur.fetchone()
    existe = (r["n"] if isinstance(r, dict) else r[0]) > 0
    if not existe:
        cur.execute("ALTER TABLE codigos_activacion "
                    "ADD COLUMN stripe_session_id VARCHAR(255) NULL UNIQUE, "
                    "ADD COLUMN email_cliente VARCHAR(255) NULL")


def revertir(cur):
    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='codigos_activacion'
              AND COLUMN_NAME='stripe_session_id'
    """)
    r = cur.fetchone()
    existe = (r["n"] if isinstance(r, dict) else r[0]) > 0
    if existe:
        cur.execute("ALTER TABLE codigos_activacion "
                    "DROP COLUMN stripe_session_id, DROP COLUMN email_cliente")
    cur.execute("DROP TABLE IF EXISTS cuentas_web_central")
