"""
Migración 0359 — PayPal como alternativa a Stripe en la web oficial (petición explícita,
2026-11-23): columnas nuevas para guardar el identificador de la Suscripción de PayPal, en vez de
forzarlo dentro de las columnas `stripe_*` (que seguirían significando lo que ya significan).

`altas_web_stripe.stripe_session_id` (la clave de idempotencia de `alta_comercial.confirmar_pago`/
`confirmar_financiacion`) se sigue reutilizando tal cual para los altas por PayPal, guardando ahí
`f"paypal_{subscription_id}"` — sigue siendo un identificador único de la operación de alta, con
PayPal o con Stripe, no hace falta una columna aparte para eso.
"""

VERSION = "0359"
DESCRIPCION = "Columnas paypal_subscription_id en suscripciones y altas_web_stripe"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "suscripciones", "paypal_subscription_id"):
        cur.execute("ALTER TABLE suscripciones ADD COLUMN paypal_subscription_id "
                   "VARCHAR(64) DEFAULT NULL")
    if not _tiene_columna(cur, "altas_web_stripe", "paypal_subscription_id"):
        cur.execute("ALTER TABLE altas_web_stripe ADD COLUMN paypal_subscription_id "
                   "VARCHAR(64) DEFAULT NULL")


def revertir(cur):
    for tabla in ("suscripciones", "altas_web_stripe"):
        if _tiene_columna(cur, tabla, "paypal_subscription_id"):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN paypal_subscription_id")
