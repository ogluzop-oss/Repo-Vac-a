"""
Migración 0276 — Facturación de uso de IA (Fase B): separa el cobro de uso de IA de la cuota
fija de suscripción.

`facturas_saas.concepto` distingue QUÉ representa cada factura de la tabla (aditiva sobre el
campo escalar `importe` ya existente, sin duplicar el esquema ni crear una segunda tabla de
facturas): 'suscripcion' (cuota fija mensual/trimestral/anual, comportamiento YA existente, ahora
explícito) | 'ia_uso' (coste acumulado de uso real de la API de Anthropic, Fase A
`ai_usage_logs`/`services/ia_control_uso.py`, cobrado APARTE de la suscripción — nunca fusionado
en la misma línea/importe, requisito explícito del negocio: "cobrar el coste por uso de la API
aparte de su tarifa mensual de suscripción"). DEFAULT 'suscripcion' para que las facturas ya
emitidas antes de esta migración queden clasificadas correctamente sin necesidad de backfill.

`ia_facturacion_periodos` = límite de IDEMPOTENCIA de la facturación de uso de IA (mismo
principio que `proximo_cobro` en `suscripciones` hace idempotente a
`facturacion_automatica.facturar_vencidas`, pero aquí por PERÍODO acumulativo en vez de por
ciclo fijo): una fila por cada período efectivamente facturado — la próxima corrida de
`services/saas/facturacion_ia.py::facturar_uso_ia` suma coste de `ai_usage_logs` SOLO desde el
`periodo_hasta` de la última fila de esa empresa (o desde el origen de sus logs si no tiene
ninguna), así el mismo log NUNCA se cuenta ni se cobra dos veces. Enlaza con la factura real
generada (`id_factura_saas`, NULL si el acumulado no llegó a facturarse). Mismo patrón
multiempresa que el resto del esquema SaaS: `id_empresa VARCHAR(36)`, igual que
`facturas_saas`/`suscripciones` (migración 0059) — no `CHAR(36)` como `ai_usage_logs` (0275),
para no forzar conversión de tipo al cruzar con las tablas SaaS existentes.

ADITIVA, idempotente, reversible.
"""

VERSION = "0276"
DESCRIPCION = "Facturación de uso de IA: facturas_saas.concepto + ia_facturacion_periodos"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        ALTER TABLE facturas_saas
        ADD COLUMN IF NOT EXISTS concepto VARCHAR(30) NOT NULL DEFAULT 'suscripcion'
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ia_facturacion_periodos (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NOT NULL,
            periodo_desde DATETIME DEFAULT NULL,
            periodo_hasta DATETIME NOT NULL,
            id_factura_saas INT DEFAULT NULL,
            creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_ia_fact_periodo_empresa (id_empresa, periodo_hasta)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS ia_facturacion_periodos")
    cur.execute("ALTER TABLE facturas_saas DROP COLUMN IF EXISTS concepto")
