"""
Migración 0364 — Plan de Pago del Portal (Portal B2B + Portal Proveedor), petición explícita,
2026-11-27. Tabla PARALELA a `suscripciones`/`planes_saas` (que son 1:1 con `empresas.id_empresa`,
el ERP): un `suministrador` no tiene `id_empresa` propio, así que forzarlo dentro de `suscripciones`
mezclaría dos conceptos con clave primaria distinta. `tipo_sujeto`+`id_sujeto` identifican tanto una
empresa (Portal B2B) como un proveedor (Portal Proveedor) con la misma tabla — ver
`services/portal_plan.py`.
"""

VERSION = "0364"
DESCRIPCION = "Tabla portal_suscripciones (Plan de Pago del Portal B2B/Proveedor)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_tabla(cur, tabla) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() "
        "AND table_name=%s", (tabla,))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _existe_tabla(cur, "portal_suscripciones"):
        cur.execute(
            "CREATE TABLE portal_suscripciones ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
            "tipo_sujeto VARCHAR(10) NOT NULL, "
            "id_sujeto VARCHAR(64) NOT NULL, "
            "codigo_plan VARCHAR(20) NOT NULL DEFAULT 'PORTAL', "
            "ciclo VARCHAR(10) NOT NULL, "
            "estado VARCHAR(12) NOT NULL DEFAULT 'activa', "
            "financiado_4_cuotas TINYINT(1) NOT NULL DEFAULT 0, "
            "cuotas_pagadas INT NOT NULL DEFAULT 0, "
            "stripe_customer_id VARCHAR(64) NULL, "
            "stripe_subscription_id VARCHAR(64) NULL, "
            "fecha_inicio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "proximo_cobro DATETIME NULL, "
            "cancelada_en DATETIME NULL, "
            "KEY idx_portal_susc_sujeto (tipo_sujeto, id_sujeto, estado)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    if _existe_tabla(cur, "portal_suscripciones"):
        cur.execute("DROP TABLE portal_suscripciones")
