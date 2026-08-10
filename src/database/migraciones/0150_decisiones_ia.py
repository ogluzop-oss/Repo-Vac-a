"""
Migración 0150 — Etapa C · Fase C1: Centro de Decisiones (ledger de decisiones/recomendaciones IA).

Pieza transversal que FALTA (la capa `src.services.ia` genera recomendaciones/anomalías/riesgos/
predicciones pero SIN persistencia, auditoría ni feedback). Este ledger unifica las decisiones
PROPUESTAS por toda la organización, auditable (Decision/Audit Replay), con aceptación/rechazo/
feedback supervisado. NUNCA modifica datos: solo registra propuestas.

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0150"
DESCRIPCION = "Etapa C/F1: decisiones_ia (Centro de Decisiones, ledger auditable de propuestas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("decisiones_ia", """
        id                BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa        CHAR(36)              DEFAULT NULL,
        dominio           VARCHAR(40)           DEFAULT NULL,   -- inventario/ventas/tesoreria/…
        tipo              VARCHAR(20)  NOT NULL DEFAULT 'recomendacion', -- recomendacion|anomalia|riesgo|prediccion
        origen            VARCHAR(40)           DEFAULT NULL,   -- ia.recomendaciones|ia.anomalias|…
        titulo            VARCHAR(160)          DEFAULT NULL,
        descripcion       VARCHAR(500)          DEFAULT NULL,
        entidad           VARCHAR(40)           DEFAULT NULL,
        entidad_ref       VARCHAR(80)           DEFAULT NULL,
        prioridad         VARCHAR(10)  NOT NULL DEFAULT 'MEDIA', -- ALTA|MEDIA|BAJA|INFO
        workflow_sugerido VARCHAR(60)           DEFAULT NULL,
        confianza         DECIMAL(5,4)          DEFAULT NULL,
        datos             MEDIUMTEXT,                            -- JSON auditable (justificación)
        estado            VARCHAR(12)  NOT NULL DEFAULT 'propuesta', -- propuesta|aceptada|rechazada|caducada
        feedback          VARCHAR(255)          DEFAULT NULL,
        clave             VARCHAR(200)          DEFAULT NULL,    -- dedup de propuestas abiertas
        correlation_id    VARCHAR(80)           DEFAULT NULL,
        actor             VARCHAR(120)          DEFAULT NULL,
        ts_creado         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_resuelto       DATETIME              DEFAULT NULL,
        INDEX idx_dec_estado (id_empresa, estado, prioridad),
        INDEX idx_dec_dominio (id_empresa, dominio),
        INDEX idx_dec_tipo (id_empresa, tipo),
        INDEX idx_dec_clave (id_empresa, clave)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
