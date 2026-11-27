"""
Migración 0368 — PayPal como alternativa a Stripe en el Plan de Pago del Portal (petición
explícita, 2026-11-27): mismo criterio exacto que `0359_paypal_web_oficial.py` para el ERP —
columna nueva para el identificador de la Suscripción de PayPal, sin forzarlo dentro de las
columnas `stripe_*` (que siguen significando lo que ya significan).

Pago DIRECTO a la cuenta de Smart Manager (como ya hace Stripe aquí) — esto NO es el PayPal
marketplace de los portales (`tpv.pagos.paypal_connect`, pago directo al PROVEEDOR): el Plan de
Pago del Portal es ingreso propio de Smart Manager, con sus credenciales PAYPAL_CLIENT_ID/
PAYPAL_CLIENT_SECRET globales de siempre (las mismas que usa `sitio_oficial` para las suscripciones
ERP) — nunca custodia ni reparto de un pago ajeno.
"""

VERSION = "0368"
DESCRIPCION = "Columna paypal_subscription_id en portal_suscripciones"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "portal_suscripciones", "paypal_subscription_id"):
        cur.execute("ALTER TABLE portal_suscripciones ADD COLUMN paypal_subscription_id "
                   "VARCHAR(64) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, "portal_suscripciones", "paypal_subscription_id"):
        cur.execute("ALTER TABLE portal_suscripciones DROP COLUMN paypal_subscription_id")
