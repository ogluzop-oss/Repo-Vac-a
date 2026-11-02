"""
Migración 0285 — Control de uso/coste y facturación de voz (ElevenLabs) por empresa, con margen
de reventa (Fase A+B+C del MISMO patrón ya usado para IA/Anthropic en 0275/0276, aplicado aquí a
SOMA TTS/ElevenLabs — ver `services/voz_control_uso.py`, `services/saas/voz_plan.py`,
`services/saas/facturacion_voz.py`).

`empresas.voice_monthly_limit_chars` INT NULL — a diferencia de `ai_daily_cost_limit_usd` (NOT
NULL, límite SIEMPRE activo en el plan LIMITED), aquí NULL significa explícitamente "sin límite":
no existe hoy un concepto de "plan" de voz (LIMITED/PAY_AS_YOU_GO) separado, así que el propio
valor NULL hace ese papel de forma más simple, sin una columna de plan adicional que nadie ha
pedido. Es un límite de SEGURIDAD mensual de caracteres (el "saldo/crédito" del encargo), no un
precio — lo ajusta la propia empresa, igual que `ai_daily_cost_limit_usd` en su self-service.

`voice_billing_config` — tabla de UNA fila global (id=1, igual que otras tablas de configuración
global de una sola fila en este esquema), con la tarifa de REVENTA (coste real del proveedor +
margen %). Semilla con los valores de ejemplo del propio encargo: coste $0.00003/carácter, margen
100% → precio de venta $0.00006/carácter. Editable SOLO desde el Panel del Fundador
(`backend_central/rutas_admin.py` + `services/saas/voz_plan.py::actualizar_tarifa_global`) — nunca
hardcodeada en código de ahí en adelante.

`voice_usage_logs` — el "VoiceUsage" del encargo (nombrado en español, como el resto del esquema):
una fila por cada síntesis REAL de ElevenLabs, con el coste base del proveedor y el importe YA con
margen aplicado en el momento (nunca recalculado con una tarifa posterior, mismo criterio que
`ai_usage_logs`). DECIMAL(12,8) — NO DECIMAL(10,6) como `ai_usage_logs` — porque el coste por
CARÁCTER de ElevenLabs es un orden de magnitud más pequeño que el coste por TOKEN de Anthropic
($0.00003/carácter vs. $3-15/1M tokens): con 6 decimales, una síntesis corta redondearía a 0.000000
y la suma mensual perdería precisión real.

`voz_facturacion_periodos` — copia exacta de `ia_facturacion_periodos` (0276): idempotencia de la
facturación de uso de voz por períodos acumulativos, independiente del ciclo de facturación de IA.

ADITIVA, idempotente, reversible.
"""

VERSION = "0285"
DESCRIPCION = "Control de uso/coste y facturación de voz (ElevenLabs): empresas.voice_monthly_limit_chars + voice_billing_config + voice_usage_logs + voz_facturacion_periodos"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        ALTER TABLE empresas
        ADD COLUMN IF NOT EXISTS voice_monthly_limit_chars INT NULL DEFAULT NULL
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_billing_config (
            id INT NOT NULL PRIMARY KEY,
            cost_basis_per_char_usd DECIMAL(12,8) NOT NULL DEFAULT 0.00003000,
            margen_pct DECIMAL(6,2) NOT NULL DEFAULT 100.00,
            actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_por VARCHAR(120) DEFAULT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        INSERT IGNORE INTO voice_billing_config (id, cost_basis_per_char_usd, margen_pct)
        VALUES (1, 0.00003000, 100.00)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_usage_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_usuario INT DEFAULT NULL,
            voice_id VARCHAR(64) DEFAULT NULL,
            character_count INT NOT NULL DEFAULT 0,
            cost_basis_usd DECIMAL(12,8) NOT NULL DEFAULT 0,
            billed_amount_usd DECIMAL(12,8) NOT NULL DEFAULT 0,
            creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_voice_usage_empresa_fecha (id_empresa, creado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voz_facturacion_periodos (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NOT NULL,
            periodo_desde DATETIME DEFAULT NULL,
            periodo_hasta DATETIME NOT NULL,
            id_factura_saas INT DEFAULT NULL,
            creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_voz_fact_periodo_empresa (id_empresa, periodo_hasta)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS voz_facturacion_periodos")
    cur.execute("DROP TABLE IF EXISTS voice_usage_logs")
    cur.execute("DROP TABLE IF EXISTS voice_billing_config")
    cur.execute("""
        ALTER TABLE empresas
        DROP COLUMN IF EXISTS voice_monthly_limit_chars
    """)
