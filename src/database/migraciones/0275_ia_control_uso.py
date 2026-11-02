"""
Migración 0275 — Control de uso y coste de IA (Anthropic) por empresa (Fase A — fundación).

Añade a `empresas` el plan de consumo de IA (`ai_plan_type`: LIMITED/PAY_AS_YOU_GO), el límite
diario de seguridad (`ai_daily_cost_limit_usd`, solo aplica en LIMITED) y el estado derivado
(`ai_status`: ACTIVE/BLOCKED_DAILY_LIMIT) que PERSISTE el bloqueo cuando se supera el límite —
así el bloqueo sobrevive a reinicios de proceso y es visible para cualquier lector de `empresas`
(GUI/API), no solo para quien lo detectó. Lo gestiona `services/ia_control_uso.py::verificar_acceso_ia`.

`ai_usage_logs` = auditoría de CADA llamada real a la API de Anthropic (los 3 puntos de llamada
reales del sistema: `translate` en `utils/ai_translator.py`, `import_mapping` en
`services/importacion/mapeo_ia.py`, `invoice_ocr` en `services/contabilidad/factura_ocr_ia.py`),
con los tokens reales devueltos por `response.usage` y el coste estimado
(`services/ia_control_uso.py::AIPriceCalculator`). `estimated_cost_usd` es DECIMAL(10,6) — no
DECIMAL(10,2) — porque una sola llamada puede costar fracciones de céntimo; redondear a 2
decimales dejaría muchas llamadas en 0.00 e invalidaría la suma diaria que usa `verificar_acceso_ia`
para decidir el bloqueo.

Mismo patrón multiempresa del resto del esquema (`id_empresa CHAR(36)` + índice compuesto con la
fecha, mismo criterio que `migracion_lotes_staging` en 0272). ADITIVA, idempotente, reversible.
"""

VERSION = "0275"
DESCRIPCION = "Control de uso/coste de IA por empresa: empresas.ai_* + ai_usage_logs"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        ALTER TABLE empresas
        ADD COLUMN IF NOT EXISTS ai_plan_type VARCHAR(20) NOT NULL DEFAULT 'LIMITED',
        ADD COLUMN IF NOT EXISTS ai_daily_cost_limit_usd DECIMAL(10,2) NOT NULL DEFAULT 10.00,
        ADD COLUMN IF NOT EXISTS ai_status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_usuario INT DEFAULT NULL,
            feature_name VARCHAR(60) NOT NULL,
            model_used VARCHAR(80) NOT NULL,
            input_tokens INT NOT NULL DEFAULT 0,
            output_tokens INT NOT NULL DEFAULT 0,
            cached_input_tokens INT NOT NULL DEFAULT 0,
            estimated_cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
            creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_ai_usage_empresa_fecha (id_empresa, creado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS ai_usage_logs")
    cur.execute("""
        ALTER TABLE empresas
        DROP COLUMN IF EXISTS ai_plan_type,
        DROP COLUMN IF EXISTS ai_daily_cost_limit_usd,
        DROP COLUMN IF EXISTS ai_status
    """)
