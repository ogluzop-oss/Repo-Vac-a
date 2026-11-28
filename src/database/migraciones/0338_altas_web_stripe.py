"""
Migración 0338 — Idempotencia de altas web (Stripe Checkout → aprovisionamiento). ADITIVA.

El alta de un cliente nuevo desde el sitio oficial (`src.services.alta_comercial`) crea una
empresa + centro + código de aprovisionamiento (`services.provisioning`, el MISMO mecanismo que
ya usa "Configuración → Datos de empresa → Centros" para emparejar un ordenador nuevo con una
empresa EXISTENTE) tras un pago real confirmado en Stripe Checkout. Esta tabla evita crear DOS
empresas para el MISMO pago si tanto la página de éxito como el webhook llegan a confirmarlo
(ambos caminos son idempotentes por `stripe_session_id`).
"""

VERSION = "0338"
DESCRIPCION = "Idempotencia de altas web por Stripe Checkout (altas_web_stripe)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS altas_web_stripe (
            id                        INT AUTO_INCREMENT PRIMARY KEY,
            stripe_session_id         VARCHAR(255) NOT NULL,
            email                     VARCHAR(255) NOT NULL,
            id_empresa                CHAR(36)     NOT NULL,
            id_centro                 CHAR(36)     NOT NULL,
            codigo_aprovisionamiento  VARCHAR(16)  NOT NULL,
            plan                      VARCHAR(30)  NOT NULL,
            creado_en                 DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_altas_web_session (stripe_session_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS altas_web_stripe")
