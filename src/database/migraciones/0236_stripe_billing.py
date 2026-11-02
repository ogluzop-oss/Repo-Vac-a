"""
Migración 0236 — Columnas de Stripe en `suscripciones` (Fase 5, ver plan `hazy-riding-aurora`).
`stripe_customer_id`/`stripe_payment_method_id` correlacionan la suscripción con el Customer y el
PaymentMethod SEPA que crea `services.saas.billing.stripe_gateway` a partir del IBAN ya domiciliado
(`iban_cifrado`, migración 0233) — no se guarda ningún dato de pago en claro, solo los identificadores
que Stripe asigna. También es la única correlación fiable para resolver la empresa desde un webhook
de Stripe (que solo trae el `customer` de Stripe, nunca el `id_empresa`).
"""

VERSION = "0236"
DESCRIPCION = "Columnas de Stripe (customer/payment method) en suscripciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = [
    ("stripe_customer_id", "VARCHAR(64) NULL"),
    ("stripe_payment_method_id", "VARCHAR(64) NULL"),
]


def aplicar(cur):
    for nombre, definicion in _COLUMNAS:
        cur.execute(f"SHOW COLUMNS FROM suscripciones LIKE '{nombre}'")
        if not cur.fetchone():
            cur.execute(f"ALTER TABLE suscripciones ADD COLUMN {nombre} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_COLUMNAS):
        cur.execute(f"SHOW COLUMNS FROM suscripciones LIKE '{nombre}'")
        if cur.fetchone():
            cur.execute(f"ALTER TABLE suscripciones DROP COLUMN {nombre}")
