"""
Migración 0233 — Domiciliación bancaria de la suscripción SaaS (cuenta para el cobro mensual).

Añade a `suscripciones` (migr. 0059) el IBAN de domiciliación de la empresa, CIFRADO en reposo con
la misma utilidad de cifrado ya usada para otros secretos de la app (`utils.cripto`, Fernet — ver
MFA en `services/seguridad/mfa.py`); no se crea un motor de cifrado paralelo. La UI (`gui/saas_admin.py`)
nunca muestra el IBAN completo tras guardarlo — solo los 4 últimos dígitos, el resto enmascarado.
ADITIVA, idempotente, reversible.
"""

VERSION = "0233"
DESCRIPCION = "Columna suscripciones.iban_cifrado (domiciliación bancaria, cifrada en reposo)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM suscripciones LIKE 'iban_cifrado'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE suscripciones ADD COLUMN iban_cifrado VARCHAR(255) NULL")
    cur.execute("SHOW COLUMNS FROM suscripciones LIKE 'iban_ultimos4'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE suscripciones ADD COLUMN iban_ultimos4 VARCHAR(4) NULL")


def revertir(cur):
    for col in ("iban_cifrado", "iban_ultimos4"):
        cur.execute(f"SHOW COLUMNS FROM suscripciones LIKE '{col}'")
        if cur.fetchone():
            cur.execute(f"ALTER TABLE suscripciones DROP COLUMN {col}")
