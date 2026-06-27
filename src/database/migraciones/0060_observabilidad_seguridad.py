"""
Migración 0060 — Observabilidad + Seguridad avanzada. ADITIVA, idempotente, reversible.

NO toca tablas existentes (usuarios/sesiones/auditoria_logs permanecen). Añade: MFA (TOTP) +
recovery codes, incidentes de seguridad + eventos, y solicitudes RGPD. Multiempresa donde aplica.
"""

VERSION = "0060"
DESCRIPCION = "Obs/Sec: MFA, recovery codes, incidentes_seguridad, eventos_incidentes, rgpd_solicitudes"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("mfa_usuarios", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL,
        secreto VARCHAR(255) NOT NULL,
        activo TINYINT NOT NULL DEFAULT 0,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mfa (id_usuario)"""),
    ("mfa_recovery_codes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL,
        codigo_hash VARCHAR(255) NOT NULL,
        usado TINYINT NOT NULL DEFAULT 0,
        usado_en DATETIME DEFAULT NULL,
        INDEX idx_recov (id_usuario, usado)"""),
    ("incidentes_seguridad", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        tipo VARCHAR(40) NOT NULL,
        severidad VARCHAR(10) NOT NULL DEFAULT 'media',
        estado VARCHAR(14) NOT NULL DEFAULT 'abierto',
        id_usuario INT DEFAULT NULL,
        ip_origen VARCHAR(64) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        cerrado_en DATETIME DEFAULT NULL,
        INDEX idx_inc (id_empresa, estado, tipo)"""),
    ("eventos_incidentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_incidente INT NOT NULL,
        accion VARCHAR(24) NOT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evinc (id_incidente)"""),
    ("rgpd_solicitudes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(16) NOT NULL,
        sujeto_tipo VARCHAR(16) NOT NULL DEFAULT 'cliente',
        sujeto_id VARCHAR(64) DEFAULT NULL,
        sujeto_nif VARCHAR(20) DEFAULT NULL,
        estado VARCHAR(14) NOT NULL DEFAULT 'pendiente',
        resultado_ruta VARCHAR(512) DEFAULT NULL,
        solicitante VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        resuelto_en DATETIME DEFAULT NULL,
        INDEX idx_rgpd (id_empresa, tipo, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
