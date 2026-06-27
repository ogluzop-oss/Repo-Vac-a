"""
Migración 0061 — Disaster Recovery (snapshots) + CRM comercial. ADITIVA, idempotente, reversible.

NO toca tablas existentes (backup/clientes/ventas permanecen). DR: registro de snapshots PITR.
CRM: leads, fuentes/etiquetas, pipeline/etapas, oportunidades, actividades, y CRM SaaS (funnel
del propio Smart Manager). Multiempresa.
"""

VERSION = "0061"
DESCRIPCION = "DR snapshots + CRM (leads, pipeline, oportunidades, actividades, crm_saas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("dr_snapshots", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'full',
        ruta VARCHAR(512) DEFAULT NULL,
        backend VARCHAR(16) NOT NULL DEFAULT 'local',
        ref_remota VARCHAR(512) DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        tamano_bytes BIGINT DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'ok',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_dr_snap (id_empresa, creado_en)"""),
    ("dr_drills", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        tipo VARCHAR(24) NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'ok',
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_dr_drill (tipo, fecha)"""),
    ("crm_lead_fuentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        UNIQUE KEY uq_crm_fuente (id_empresa, codigo)"""),
    ("crm_leads", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        empresa VARCHAR(160) DEFAULT NULL,
        email VARCHAR(160) DEFAULT NULL,
        telefono VARCHAR(40) DEFAULT NULL,
        fuente VARCHAR(40) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'nuevo',
        valor_estimado DECIMAL(14,2) NOT NULL DEFAULT 0,
        prioridad VARCHAR(10) NOT NULL DEFAULT 'normal',
        responsable INT DEFAULT NULL,
        score INT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        etiquetas VARCHAR(255) DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_ultimo_contacto DATETIME DEFAULT NULL,
        INDEX idx_crm_lead (id_empresa, estado, responsable)"""),
    ("crm_pipelines", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_crm_pipe (id_empresa, codigo)"""),
    ("crm_etapas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_pipeline INT NOT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        probabilidad INT NOT NULL DEFAULT 0,
        color VARCHAR(12) DEFAULT NULL,
        es_ganado TINYINT NOT NULL DEFAULT 0,
        es_perdido TINYINT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_crm_etapa (id_pipeline, codigo),
        INDEX idx_crm_etapa (id_empresa, id_pipeline, orden)"""),
    ("crm_oportunidades", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        titulo VARCHAR(160) NOT NULL,
        id_pipeline INT DEFAULT NULL,
        id_etapa INT DEFAULT NULL,
        id_lead INT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        valor DECIMAL(14,2) NOT NULL DEFAULT 0,
        probabilidad INT NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        responsable INT DEFAULT NULL,
        fecha_cierre_prevista DATE DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_cierre DATETIME DEFAULT NULL,
        motivo_perdida VARCHAR(160) DEFAULT NULL,
        INDEX idx_crm_op (id_empresa, estado, id_etapa)"""),
    ("crm_actividades", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'seguimiento',
        asunto VARCHAR(200) DEFAULT NULL,
        id_lead INT DEFAULT NULL,
        id_oportunidad INT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        responsable INT DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        vencimiento DATETIME DEFAULT NULL,
        notas TEXT DEFAULT NULL,
        ref_tarea INT DEFAULT NULL,
        ref_evento INT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_crm_act (id_empresa, tipo, estado)"""),
    ("crm_saas_funnel", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        email VARCHAR(160) DEFAULT NULL,
        plan_interes VARCHAR(30) DEFAULT NULL,
        fase VARCHAR(16) NOT NULL DEFAULT 'lead',
        id_empresa_creada VARCHAR(36) DEFAULT NULL,
        valor_estimado DECIMAL(14,2) NOT NULL DEFAULT 0,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_conversion DATETIME DEFAULT NULL,
        INDEX idx_crm_saas (fase)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
